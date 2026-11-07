"""Sign-in endpoints for the browser UI. Open (no auth) by design: they are how you get a session."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from backend.api import auth, session

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/config")
def config_():
    return {"mode": auth.mode(), "github": session.enabled()}


@router.get("/me")
def me(request: Request):
    """Who am I? 200 with the identity, or 401. Works for a session cookie or an API key."""
    p = auth.current_principal(request)
    if p is None:
        return {"authenticated": False, "mode": "off", "name": None, "roles": []}
    return {"authenticated": True, "mode": auth.mode(), "name": p.display, "login": p.upn or None, "roles": sorted(p.roles)}


@router.get("/github/login")
def github_login():
    if not session.enabled():
        return JSONResponse({"error": {"code": "not_found", "message": "GitHub sign-in is not configured."}}, status_code=404)
    state = session.new_state()
    resp = RedirectResponse(session.authorize_url(state), status_code=302)
    resp.set_cookie(session.STATE_COOKIE, state, max_age=600, httponly=True, samesite="lax", secure=session.secure_cookies(), path="/api/auth")
    return resp


def _page(title: str, body: str, status: int) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><meta charset=utf-8><title>{title}</title><body style='font-family:sans-serif;max-width:32rem;margin:4rem auto'>"
                        f"<h1>{title}</h1><p>{body}</p><p><a href='/'>Back to the app</a></p>", status_code=status)


@router.get("/github/callback")
def github_callback(request: Request, code: str = "", state: str = ""):
    if not session.enabled():
        return _page("Not configured", "GitHub sign-in is not configured.", 404)
    if not session.same_state(state, request.cookies.get(session.STATE_COOKIE, "")):
        return _page("Sign-in failed", "The sign-in request could not be verified. Please start again.", 400)
    try:
        gh = session.exchange_code(code)
    except ValueError as e:
        return _page("Sign-in failed", str(e), 502)
    role = session.users().get(gh["login"].lower())
    if role is None:                                   # signed in at GitHub, but not on the allow-list
        return _page("Access not granted", f"The GitHub account <b>{gh['login']}</b> is not allowed to use this app. Ask the owner to add it.", 403)
    resp = RedirectResponse("/app", status_code=302)
    resp.set_cookie(session.COOKIE, session.make_session(gh["id"], gh["login"], gh["name"], role), max_age=session.hours() * 3600,
                    httponly=True, samesite="lax", secure=session.secure_cookies(), path="/")
    resp.delete_cookie(session.STATE_COOKIE, path="/api/auth")
    return resp


@router.post("/logout")
def logout():
    resp = JSONResponse({"signed_out": True})
    resp.delete_cookie(session.COOKIE, path="/")
    return resp
