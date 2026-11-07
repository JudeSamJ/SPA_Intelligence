"""Microsoft Entra ID (Azure AD) bearer-token authentication and role checks.

AUTH_MODE=off    (default) no authentication: local development and the test stub server only.
AUTH_MODE=entra  every /api route except /health requires a valid Entra access token for THIS API.
AUTH_MODE=apikey every /api route except /health requires an X-API-Key header matching a key in API_KEYS. For demos where
                 Entra app registrations are not available. Same roles, same checks; keys are shared secrets, so use them only
                 with demo data, over HTTPS, and rotate them after the demo.

A token is accepted only if: RS256 signature verifies against the tenant's published keys (JWKS), the audience is this
API (ENTRA_CLIENT_ID or api://ENTRA_CLIENT_ID), the issuer is this tenant, the tenant id matches, and it has not expired.
Authorisation uses Entra *app roles* in the token's `roles` claim:

  Spa.Staff     read everything for staff (contracts, gap, simulations, obligations, playbook, cross-check, ERP preview)
  Spa.Reviewer  everything Staff can do, plus actions that change data or spend LLM calls (review, upload/extract,
                golden export, jurisdiction, eval runs, ERP push)
  Spa.Buyer     only POST /buyer/chat, and only for the contract mapped to that person in BUYER_ACCOUNTS

No secret is needed by the API: it only verifies signatures with public keys. Nothing from a token is ever logged
except a short hash of the object id (see app/buyer.py).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

import httpx
import jwt
from fastapi import Request

from backend.api.deps import ApiError

log = logging.getLogger("spa.auth")

STAFF, REVIEWER, BUYER = "Spa.Staff", "Spa.Reviewer", "Spa.Buyer"
READ_ROLES = {STAFF, REVIEWER}
WRITE_ROLES = {REVIEWER}
# POST routes that only compute and return results (no stored change, no LLM spend): Staff may call them.
READ_ONLY_POSTS = [re.compile(p) for p in (
    r"/penalty$", r"/cashflow$", r"/chat$", r"/statute-gap$", r"/montecarlo$", r"/portfolio/montecarlo$",
    r"/erp/export$", r"/alerts/[^/]+/ack$", r"/alerts/recompute$")]


@dataclass
class Principal:
    oid: str
    name: str
    upn: str
    roles: set[str]
    tenant: str
    raw_claims: dict = field(default_factory=dict, repr=False)
    contract: str | None = None          # apikey mode: the contract a buyer key is bound to

    @property
    def display(self) -> str:
        return (self.name or self.upn or self.oid)[:80]


def mode() -> str:
    m = (os.environ.get("AUTH_MODE") or "off").strip().lower()
    return m if m in ("off", "entra", "apikey") else "off"


def settings() -> tuple[str, str]:
    return os.environ.get("ENTRA_TENANT_ID", "").strip(), os.environ.get("ENTRA_CLIENT_ID", "").strip()


def check_startup() -> None:
    """Fail closed: asking for Entra mode without the settings must stop the server, not silently open it."""
    if mode() == "entra":
        tenant, client = settings()
        if not tenant or not client:
            raise RuntimeError("AUTH_MODE=entra needs ENTRA_TENANT_ID and ENTRA_CLIENT_ID.")
    elif mode() == "apikey":
        from backend.api import session
        session.check_startup()
        if not api_keys() and not session.enabled():
            raise RuntimeError("AUTH_MODE=apikey needs API_KEYS with at least one valid key (24+ characters).")
    elif os.environ.get("AUTH_MODE", "off").strip().lower() not in ("off", ""):
        raise RuntimeError(f"Unknown AUTH_MODE '{os.environ.get('AUTH_MODE')}' (use off, entra or apikey).")
    else:
        log.warning("Authentication is OFF (AUTH_MODE=off): use only for local development.")


# ------------------------------------------------------------------ signing keys
_jwks_cache: dict = {"at": 0.0, "keys": None}
_jwks_lock = threading.Lock()
JWKS_TTL = 3600
JWKS_FETCHER: Callable[[str], dict] | None = None      # tests inject a fetcher: no network in tests


def _fetch_jwks(tenant: str) -> dict:
    if JWKS_FETCHER is not None:
        return JWKS_FETCHER(tenant)
    r = httpx.get(f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys", timeout=10)
    r.raise_for_status()
    return r.json()


def _signing_key(kid: str, tenant: str):
    with _jwks_lock:
        fresh = _jwks_cache["keys"] is not None and time.time() - _jwks_cache["at"] < JWKS_TTL
        for attempt in (0, 1):
            if not fresh or attempt:                     # unknown kid after a cache hit: refresh once (key rollover)
                _jwks_cache["keys"], _jwks_cache["at"] = _fetch_jwks(tenant), time.time()
            for k in _jwks_cache["keys"].get("keys", []):
                if k.get("kid") == kid:
                    return jwt.PyJWK(k).key
            fresh = False
    raise ApiError(401, "unauthorized", "Signing key not recognised.")


def reset_cache() -> None:
    _jwks_cache.update(at=0.0, keys=None)


# ------------------------------------------------------------------ token validation
def validate_token(token: str) -> Principal:
    tenant, client = settings()
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not header.get("kid"):
            raise ApiError(401, "unauthorized", "Unsupported token.")
        key = _signing_key(header["kid"], tenant)
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=[client, f"api://{client}"],
                            options={"require": ["exp", "aud", "iss"]}, leeway=60)
    except ApiError:
        raise
    except jwt.ExpiredSignatureError:
        raise ApiError(401, "token_expired", "The access token has expired.") from None
    except jwt.PyJWTError:
        raise ApiError(401, "unauthorized", "Invalid access token.") from None
    except httpx.HTTPError:
        raise ApiError(503, "auth_unavailable", "Could not fetch the identity provider's signing keys.") from None
    if claims.get("tid") != tenant or claims["iss"] not in (f"https://login.microsoftonline.com/{tenant}/v2.0",
                                                           f"https://sts.windows.net/{tenant}/"):
        raise ApiError(401, "unauthorized", "Token is from a different tenant.")
    roles = claims.get("roles") or []
    return Principal(oid=str(claims.get("oid") or claims.get("sub") or ""), name=str(claims.get("name") or ""),
                     upn=str(claims.get("preferred_username") or claims.get("upn") or ""),
                     roles={r for r in roles if isinstance(r, str)}, tenant=tenant, raw_claims={})


def api_keys() -> dict[str, dict]:
    """API_KEYS = JSON {"<key, 24+ chars>": {"name": "Demo staff", "roles": ["Spa.Reviewer"], "contract": "<64-hex, buyers only>"}}.
    Entries that are malformed or have short keys are ignored (never accepted)."""
    raw = os.environ.get("API_KEYS", "").strip()
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    out = {}
    for k, v in (data.items() if isinstance(data, dict) else []):
        if isinstance(k, str) and len(k) >= 24 and isinstance(v, dict) and isinstance(v.get("roles"), list):
            c = v.get("contract")
            if c is None or (isinstance(c, str) and re.fullmatch(r"[0-9a-f]{64}", c)):
                out[k] = {"name": str(v.get("name") or "API key")[:60], "roles": {r for r in v["roles"] if isinstance(r, str)}, "contract": c}
    return out


def validate_api_key(key: str) -> Principal:
    found = None
    for k, v in api_keys().items():                      # compare against every key: no early exit on a match
        if hmac.compare_digest(k.encode(), key.encode()):
            found = v
    if found is None:
        raise ApiError(401, "unauthorized", "Invalid API key.")
    return Principal(oid="key:" + hashlib.sha256(key.encode()).hexdigest()[:12], name=found["name"], upn="", roles=found["roles"],
                     tenant="", contract=found["contract"])


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer ") or len(h) < 20:
        raise ApiError(401, "unauthorized", "Sign in required: missing bearer token.")
    return h[7:].strip()


# ------------------------------------------------------------------ FastAPI dependencies
def _session_principal(request: Request) -> Principal | None:
    """A GitHub-sign-in session cookie. State-changing requests must also carry X-Requested-With (CSRF defence)."""
    from backend.api import session
    if not session.enabled():
        return None
    c = session.read_session(request.cookies.get(session.COOKIE, ""))
    if c is None:
        return None
    if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get("x-requested-with", "").lower() != "spa":
        raise ApiError(403, "forbidden", "Missing X-Requested-With header.")
    return Principal(oid=c["sub"], name=str(c.get("name") or c.get("login") or ""), upn=str(c.get("login") or ""),
                     roles={c["role"]}, tenant="github")


def current_principal(request: Request) -> Principal | None:
    """None in AUTH_MODE=off. Otherwise a validated principal (cached on the request)."""
    if mode() == "off":
        return None
    p = getattr(request.state, "principal", None)
    if p is None:
        if mode() == "apikey":
            key = request.headers.get("x-api-key", "").strip()
            if key:
                p = validate_api_key(key)
            else:
                p = _session_principal(request)
                if p is None:
                    raise ApiError(401, "unauthorized", "Sign in, or send an X-API-Key header.")
        else:
            p = validate_token(_bearer(request))
        request.state.principal = p
    return p


def _needs_write(request: Request) -> bool:
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return False
    return not any(rx.search(request.url.path) for rx in READ_ONLY_POSTS)


def staff_access(request: Request) -> None:
    """Applied to every staff-side router. Buyers are refused here: their only route is /buyer/chat."""
    p = current_principal(request)
    if p is None:
        return
    need = WRITE_ROLES if _needs_write(request) else READ_ROLES
    if not (p.roles & need):
        log.info("403 %s %s role=%s", request.method, request.url.path, sorted(p.roles))
        raise ApiError(403, "forbidden", "Your account does not have the role required for this action.")


def actor(request: Request, fallback: str = "") -> str:
    """Who did it: the verified identity when auth is on, never a name typed into a request body."""
    p = getattr(request.state, "principal", None)
    return p.display if p else (fallback or "anonymous")


# ------------------------------------------------------------------ buyer mapping
def buyer_accounts() -> dict[str, str]:
    """BUYER_ACCOUNTS = JSON {"<entra object id>": "<64-hex contract id>"} (or oid=id,oid=id)."""
    raw = os.environ.get("BUYER_ACCOUNTS", "").strip()
    if not raw:
        return {}
    pairs = json.loads(raw).items() if raw.startswith("{") else (p.split("=", 1) for p in re.split(r"[,;\s]+", raw) if "=" in p)
    return {str(k).strip().lower(): str(v).strip() for k, v in pairs if re.fullmatch(r"[0-9a-f]{64}", str(v).strip())}


def contract_for_principal(p: Principal) -> str | None:
    if BUYER not in p.roles:
        return None
    if mode() == "apikey":
        return p.contract
    return buyer_accounts().get(p.oid.lower())
