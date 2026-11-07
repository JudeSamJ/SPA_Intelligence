"""Microsoft Entra ID (Azure AD) bearer-token authentication and role checks.

AUTH_MODE=off    (default) no authentication: local development and the test stub server only.
AUTH_MODE=entra  every /api route except /health requires a valid Entra access token for THIS API.

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

    @property
    def display(self) -> str:
        return (self.name or self.upn or self.oid)[:80]


def mode() -> str:
    m = (os.environ.get("AUTH_MODE") or "off").strip().lower()
    return m if m in ("off", "entra") else "off"


def settings() -> tuple[str, str]:
    return os.environ.get("ENTRA_TENANT_ID", "").strip(), os.environ.get("ENTRA_CLIENT_ID", "").strip()


def check_startup() -> None:
    """Fail closed: asking for Entra mode without the settings must stop the server, not silently open it."""
    if mode() == "entra":
        tenant, client = settings()
        if not tenant or not client:
            raise RuntimeError("AUTH_MODE=entra needs ENTRA_TENANT_ID and ENTRA_CLIENT_ID.")
    elif os.environ.get("AUTH_MODE", "off").strip().lower() not in ("off", ""):
        raise RuntimeError(f"Unknown AUTH_MODE '{os.environ.get('AUTH_MODE')}' (use off or entra).")
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


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer ") or len(h) < 20:
        raise ApiError(401, "unauthorized", "Sign in required: missing bearer token.")
    return h[7:].strip()


# ------------------------------------------------------------------ FastAPI dependencies
def current_principal(request: Request) -> Principal | None:
    """None in AUTH_MODE=off. Otherwise a validated principal (cached on the request)."""
    if mode() == "off":
        return None
    p = getattr(request.state, "principal", None)
    if p is None:
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
    return buyer_accounts().get(p.oid.lower())
