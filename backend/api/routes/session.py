"""Sign-in endpoints for the browser UI. Open (no auth) by design: they are how you get a session."""
from __future__ import annotations

from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse

from backend.api import auth, session
from backend.api.deps import ApiError

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
def config_():
    from backend.api import supabase_auth
    return {"mode": auth.mode(), "github": session.enabled(), "email": supabase_auth.enabled() and auth.mode() == "supabase"}


@router.get("/me")
def me(request: Request):
    """Who am I? Always 200: {authenticated: false} when nobody is signed in (so the UI can show the login page without a failed request)."""
    mode = auth.mode()
    if mode == "off":
        return {"authenticated": False, "mode": "off", "name": None, "login": None, "avatar_url": None, "roles": []}
    try:
        p = auth.current_principal(request)
    except ApiError as e:
        if e.status == 401:
            return {"authenticated": False, "mode": mode, "name": None, "login": None, "avatar_url": None, "roles": []}
        raise
    return {"authenticated": True, "mode": mode, "name": p.display, "login": p.upn or None, "avatar_url": p.avatar, "roles": sorted(p.roles),
            "pending": mode == "supabase" and not p.roles}


@router.get("/github/login")
def github_login(next: str = ""):
    if not session.enabled():
        return JSONResponse({"error": {"code": "not_found", "message": "GitHub sign-in is not configured."}}, status_code=404)
    state = session.new_state()
    resp = RedirectResponse(session.authorize_url(state), status_code=302)
    kw = dict(max_age=600, httponly=True, samesite="lax", secure=session.secure_cookies(), path="/api/auth")
    resp.set_cookie(session.STATE_COOKIE, state, **kw)
    resp.set_cookie(session.NEXT_COOKIE, session.safe_next(next), **kw)
    return resp


def _fail(code: str, **extra) -> RedirectResponse:
    """Errors go to the themed login page, which explains them; nothing about the failure beyond a short code is exposed."""
    resp = RedirectResponse("/login?" + urlencode({"error": code, **extra}), status_code=302)
    resp.delete_cookie(session.STATE_COOKIE, path="/api/auth")
    resp.delete_cookie(session.NEXT_COOKIE, path="/api/auth")
    return resp


@router.get("/github/callback")
def github_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if not session.enabled():
        return JSONResponse({"error": {"code": "not_found", "message": "GitHub sign-in is not configured."}}, status_code=404)
    if error:                                           # the user pressed Cancel at GitHub
        return _fail("cancelled")
    if not session.same_state(state, request.cookies.get(session.STATE_COOKIE, "")):
        return _fail("state")
    try:
        gh = session.exchange_code(code)
    except ValueError:
        return _fail("failed")
    role = session.users().get(gh["login"].lower())
    if role is None:                                    # signed in at GitHub, but not on the allow-list
        return _fail("not_allowed", login=gh["login"][:39])
    resp = RedirectResponse(session.safe_next(request.cookies.get(session.NEXT_COOKIE, "")), status_code=302)
    resp.set_cookie(session.COOKIE, session.make_session(gh["id"], gh["login"], gh["name"], role, gh.get("avatar")),
                    max_age=session.hours() * 3600, httponly=True, samesite="lax", secure=session.secure_cookies(), path="/")
    resp.delete_cookie(session.STATE_COOKIE, path="/api/auth")
    resp.delete_cookie(session.NEXT_COOKIE, path="/api/auth")
    return resp


@router.post("/logout")
def logout():
    resp = JSONResponse({"signed_out": True})
    resp.delete_cookie(session.COOKIE, path="/")
    return resp
