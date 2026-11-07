"""GitHub sign-in for the browser UI (server-side OAuth authorization-code flow) and signed session cookies.

Why this exists: a browser cannot hold an API key safely, and Entra app registrations need an admin. A GitHub OAuth App can be created by
anyone. Only GitHub usernames listed in GITHUB_USERS get in, each with a role (Spa.Staff or Spa.Reviewer). Machines (Power Platform)
keep using X-API-Key.

Settings (all server-side):
  GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET   from the GitHub OAuth App
  PUBLIC_BASE_URL                          e.g. https://spa-intelligence-bkf2.onrender.com (the callback URL is built from this, never from request headers)
  SESSION_SECRET                           32+ random characters; signs the session cookie
  GITHUB_USERS                             "judesamj:Spa.Reviewer,colleague:Spa.Staff"  (login:role pairs; case-insensitive logins)
  SESSION_HOURS                            default 8

The GitHub access token is used once to read the user's id and login, then discarded; it is never stored or logged.
Cookie: HttpOnly, SameSite=Lax, Secure when PUBLIC_BASE_URL is https. State-changing requests that rely on the cookie must carry
the header X-Requested-With: spa (a cross-site page cannot add it without a CORS preflight, which we do not allow).
"""
from __future__ import annotations

import hmac
import os
import re
import secrets
import time
from urllib.parse import urlencode

import httpx
import jwt

COOKIE = "spa_session"
STATE_COOKIE = "spa_oauth_state"
ROLES = ("Spa.Staff", "Spa.Reviewer")
GITHUB_TRANSPORT: httpx.BaseTransport | None = None      # tests inject a mock: no network in tests


def enabled() -> bool:
    return bool(os.environ.get("GITHUB_CLIENT_ID", "").strip())


def users() -> dict[str, str]:
    """{login_lower: role}. Entries with an unknown role are ignored (never granted)."""
    out = {}
    for part in re.split(r"[,;\s]+", os.environ.get("GITHUB_USERS", "").strip()):
        if ":" in part:
            login, role = part.split(":", 1)
            if re.fullmatch(r"[A-Za-z0-9-]{1,39}", login) and role in ROLES:
                out[login.lower()] = role
    return out


def secret() -> str:
    return os.environ.get("SESSION_SECRET", "")


def base_url() -> str:
    return os.environ.get("PUBLIC_BASE_URL", "").strip().rstrip("/")


def check_startup() -> None:
    """Fail closed: a half-configured sign-in must stop the server, not leave a hole."""
    if not enabled():
        return
    missing = [v for v in ("GITHUB_CLIENT_SECRET", "PUBLIC_BASE_URL") if not os.environ.get(v, "").strip()]
    if missing:
        raise RuntimeError("GitHub sign-in needs " + ", ".join(missing) + ".")
    if len(secret()) < 32:
        raise RuntimeError("SESSION_SECRET must be at least 32 characters.")
    if not users():
        raise RuntimeError("GITHUB_USERS must list at least one login:role (role Spa.Staff or Spa.Reviewer).")
    if not base_url().startswith(("https://", "http://localhost", "http://127.0.0.1")):
        raise RuntimeError("PUBLIC_BASE_URL must be https (http only for localhost).")


def callback_url() -> str:
    return base_url() + "/api/auth/github/callback"


def secure_cookies() -> bool:
    return base_url().startswith("https://")


def hours() -> int:
    try:
        return max(1, min(72, int(os.environ.get("SESSION_HOURS", "8"))))
    except ValueError:
        return 8


# ------------------------------------------------------------------ session cookie
def make_session(github_id: int, login: str, name: str, role: str) -> str:
    now = int(time.time())
    return jwt.encode({"sub": f"github:{github_id}", "login": login, "name": name, "role": role,
                       "iat": now, "exp": now + hours() * 3600}, secret(), algorithm="HS256")


def read_session(token: str) -> dict | None:
    """Verified claims, or None. The allow-list is re-checked on every request, so removing a user takes effect at once."""
    if not token or not secret():
        return None
    try:
        c = jwt.decode(token, secret(), algorithms=["HS256"], options={"require": ["exp", "sub", "role"]})
    except jwt.PyJWTError:
        return None
    if users().get(str(c.get("login", "")).lower()) != c.get("role"):
        return None
    return c


# ------------------------------------------------------------------ GitHub calls
def authorize_url(state: str) -> str:
    return "https://github.com/login/oauth/authorize?" + urlencode(
        {"client_id": os.environ["GITHUB_CLIENT_ID"], "redirect_uri": callback_url(), "scope": "read:user", "state": state,
         "allow_signup": "false"})


def new_state() -> str:
    return secrets.token_urlsafe(24)


def same_state(a: str, b: str) -> bool:
    return bool(a) and bool(b) and hmac.compare_digest(a.encode(), b.encode())


def exchange_code(code: str) -> dict:
    """code -> {id, login, name}. Raises ValueError with a safe message."""
    try:
        with httpx.Client(timeout=10, transport=GITHUB_TRANSPORT) as c:
            r = c.post("https://github.com/login/oauth/access_token", headers={"Accept": "application/json"},
                       data={"client_id": os.environ["GITHUB_CLIENT_ID"], "client_secret": os.environ["GITHUB_CLIENT_SECRET"],
                             "code": code, "redirect_uri": callback_url()})
            tok = r.json().get("access_token") if r.status_code == 200 else None
            if not tok:
                raise ValueError("GitHub did not accept the sign-in code.")
            u = c.get("https://api.github.com/user", headers={"Authorization": f"Bearer {tok}", "Accept": "application/vnd.github+json"})
            if u.status_code != 200:
                raise ValueError("Could not read the GitHub profile.")
            j = u.json()
            return {"id": int(j["id"]), "login": str(j["login"]), "name": str(j.get("name") or j["login"])[:80]}
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise ValueError(str(e) if isinstance(e, ValueError) else "GitHub is unreachable.") from None
