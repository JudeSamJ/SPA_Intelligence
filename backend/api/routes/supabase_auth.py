"""Email + password sign-in through Supabase Auth. Open by design (these routes are how you get a session)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app import users
from backend.api import deps, session, supabase_auth
from backend.api.deps import ApiError

log = logging.getLogger("spa.auth")
router = APIRouter(prefix="/auth/supabase", tags=["auth"])
limiter = deps.RateLimiter(10, 60, "sign-in")
MESSAGES = {
    "invalid": "Email or password is not correct.",
    "unconfirmed": "Please confirm your email first: open the link we sent you.",
    "rate_limited": "Too many attempts. Please wait a few minutes.",
    "weak_password": f"Use a password of at least {supabase_auth.MIN_PASSWORD} characters.",
    "bad_input": "Check the email address and try again.",
    "failed": "Sign-in is not available right now. Please try again shortly.",
}


class Credentials(BaseModel):
    email: str = Field(..., max_length=254)
    password: str = Field(..., min_length=1, max_length=200)


class EmailOnly(BaseModel):
    email: str = Field(..., max_length=254)


class Reset(BaseModel):
    token: str = Field(..., min_length=10, max_length=4000)
    password: str = Field(..., min_length=1, max_length=200)


def _guard(request: Request) -> None:
    if not supabase_auth.enabled():
        raise ApiError(404, "not_found", "Email sign-in is not configured.")
    if request.headers.get("x-requested-with", "").lower() != "spa":       # a cross-site form cannot set this header
        raise ApiError(403, "forbidden", "Missing X-Requested-With header.")


def _err(f: supabase_auth.AuthFailure) -> ApiError:
    status = 401 if f.code in ("invalid", "unconfirmed") else 429 if f.code == "rate_limited" else 422 if f.code in ("weak_password", "bad_input") else 503
    return ApiError(status, f.code, MESSAGES.get(f.code, MESSAGES["failed"]))


@router.post("/login", dependencies=[Depends(limiter)])
def login(body: Credentials, request: Request):
    _guard(request)
    try:
        u = supabase_auth.sign_in(body.email, body.password)
    except supabase_auth.AuthFailure as f:
        raise _err(f) from None
    try:
        users.touch(u["id"], u["email"], u["name"])
        roles = users.principal_roles(u["id"], u["email"])
    except Exception:  # noqa: BLE001
        raise ApiError(503, "database_unavailable", "The user database is not reachable right now.") from None
    resp = JSONResponse({"authenticated": True, "pending": not roles, "email": u["email"]})
    resp.set_cookie(session.COOKIE, session.make_supabase_session(u["id"], u["email"], u["name"]), max_age=session.hours() * 3600,
                    httponly=True, samesite="lax", secure=session.secure_cookies(), path="/")
    return resp


@router.post("/signup", dependencies=[Depends(limiter)], status_code=202)
def signup(body: Credentials, request: Request):
    """Same reply whether or not the address already has an account, so this cannot be used to find out who is registered."""
    _guard(request)
    try:
        supabase_auth.sign_up(body.email, body.password, session.base_url() + "/login?confirmed=1")
    except supabase_auth.AuthFailure as f:
        if f.code not in ("invalid",):
            raise _err(f) from None
    return {"check_email": True}


@router.post("/recover", dependencies=[Depends(limiter)], status_code=202)
def recover(body: EmailOnly, request: Request):
    _guard(request)
    try:
        supabase_auth.recover(body.email, session.base_url() + "/reset")
    except supabase_auth.AuthFailure as f:
        if f.code in ("rate_limited", "bad_input"):
            raise _err(f) from None
    return {"check_email": True}


@router.post("/reset", dependencies=[Depends(limiter)])
def reset(body: Reset, request: Request):
    _guard(request)
    try:
        supabase_auth.reset_password(body.token, body.password)
    except supabase_auth.AuthFailure as f:
        raise _err(f) from None
    return {"reset": True}
