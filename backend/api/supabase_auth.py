"""Sign-in with Supabase Auth (GoTrue), done server-side so the browser never holds a Supabase token.

The app calls Supabase's Auth REST API with the project's public (anon) key, checks the answer, and issues its own HttpOnly
session cookie. Roles are NOT taken from Supabase: they come from the app_users table (see app/users.py).

Settings: SUPABASE_URL (https://<ref>.supabase.co), SUPABASE_ANON_KEY (the public key; it is safe to be known, but keep it in the
environment anyway). In Supabase turn "Confirm email" ON and add PUBLIC_BASE_URL to the redirect URLs.
"""
from __future__ import annotations

import logging
import os
import re
from urllib.parse import urlencode

import httpx

log = logging.getLogger("spa.supabase")
TRANSPORT: httpx.BaseTransport | None = None            # tests inject a mock: no network in tests
EMAIL_RE = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}$")
MIN_PASSWORD, MAX_PASSWORD = 10, 72


class AuthFailure(Exception):
    """code is one of: invalid, unconfirmed, rate_limited, weak_password, bad_input, failed."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def url() -> str:
    return os.environ.get("SUPABASE_URL", "").strip().rstrip("/")


def anon_key() -> str:
    return os.environ.get("SUPABASE_ANON_KEY", "").strip()


def enabled() -> bool:
    return bool(url() and anon_key())


def check_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e):
        raise AuthFailure("bad_input")
    return e


def check_password(pw: str) -> str:
    if not isinstance(pw, str) or not (MIN_PASSWORD <= len(pw.encode()) <= MAX_PASSWORD):
        raise AuthFailure("weak_password")
    return pw


def _call(method: str, path: str, body: dict | None = None, bearer: str | None = None, query: dict | None = None):
    headers = {"apikey": anon_key(), "Content-Type": "application/json"}
    headers["Authorization"] = f"Bearer {bearer or anon_key()}"
    u = f"{url()}/auth/v1/{path}" + ("?" + urlencode(query) if query else "")
    try:
        with httpx.Client(timeout=10, transport=TRANSPORT) as c:
            r = c.request(method, u, json=body, headers=headers)
    except httpx.HTTPError as e:
        log.warning("supabase auth unreachable: %s", type(e).__name__)
        raise AuthFailure("failed") from None
    try:
        data = r.json()
    except ValueError:
        data = {}
    return r.status_code, data if isinstance(data, dict) else {}


def _fail_from(status: int, data: dict) -> AuthFailure:
    code = str(data.get("error_code") or data.get("code") or "")
    if code == "email_not_confirmed":
        return AuthFailure("unconfirmed")
    if status == 429 or code in ("over_request_rate_limit", "over_email_send_rate_limit"):
        return AuthFailure("rate_limited")
    if code in ("weak_password", "same_password"):
        return AuthFailure("weak_password")
    if status in (400, 401, 422) and code in ("invalid_credentials", "validation_failed", "user_not_found", ""):
        return AuthFailure("invalid")                       # identical answer for "no such user" and "wrong password"
    return AuthFailure("failed")


def _user_info(user: dict) -> dict:
    meta = user.get("user_metadata") if isinstance(user.get("user_metadata"), dict) else {}
    return {"id": str(user.get("id") or ""), "email": str(user.get("email") or "").lower(),
            "name": str(meta.get("full_name") or meta.get("name") or "")[:80],
            "confirmed": bool(user.get("email_confirmed_at") or user.get("confirmed_at"))}


def sign_in(email: str, password: str) -> dict:
    """-> {id, email, name}. Requires a confirmed email."""
    status, data = _call("POST", "token", {"email": check_email(email), "password": password}, query={"grant_type": "password"})
    if status != 200:
        raise _fail_from(status, data)
    info = _user_info(data.get("user") or {})
    if not info["id"] or not info["email"]:
        raise AuthFailure("failed")
    if not info["confirmed"]:
        raise AuthFailure("unconfirmed")
    return info


def sign_up(email: str, password: str, redirect_to: str) -> None:
    """Creates the account and makes Supabase email a confirmation link. Same outcome whether or not the email already exists."""
    status, data = _call("POST", "signup", {"email": check_email(email), "password": check_password(password)},
                         query={"redirect_to": redirect_to})
    if status not in (200, 201):
        raise _fail_from(status, data)


def recover(email: str, redirect_to: str) -> None:
    """Emails a password-reset link. Always looks successful to the caller (no account enumeration)."""
    status, data = _call("POST", "recover", {"email": check_email(email)}, query={"redirect_to": redirect_to})
    if status == 429:
        raise AuthFailure("rate_limited")


def reset_password(access_token: str, new_password: str) -> None:
    """The access token comes from the recovery link. It is sent once, over TLS, and never stored or logged."""
    if not access_token or len(access_token) > 4000 or " " in access_token:
        raise AuthFailure("bad_input")
    status, data = _call("PUT", "user", {"password": check_password(new_password)}, bearer=access_token)
    if status != 200:
        raise _fail_from(status, data) if status != 401 else AuthFailure("invalid")
