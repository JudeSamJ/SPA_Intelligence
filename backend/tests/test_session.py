"""GitHub sign-in for the UI: OAuth state, allow-list, signed cookie, CSRF header, roles. GitHub is mocked."""
import json
import time
from urllib.parse import parse_qs, urlparse

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from backend.api import session
from backend.api.main import create_app
from backend.tests.test_api import env, seeded, sid  # noqa: F401  (fixtures)

SECRET = "s" * 40
KEY = "staff-key-" + "a" * 20


@pytest.fixture
def gh(env, seeded, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("API_KEYS", json.dumps({KEY: {"name": "Machine", "roles": ["Spa.Reviewer"]}}))
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid123")
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "csecret")
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.setenv("GITHUB_USERS", "Alice:Spa.Reviewer,bob:Spa.Staff,evil:Spa.Admin")
    who = {"login": "alice", "id": 11, "name": "Alice A"}
    seen = {}

    def handler(req: httpx.Request):
        if req.url.host == "github.com":
            seen["token_req"] = dict(httpx.QueryParams(req.content.decode()))
            return httpx.Response(200, json={"access_token": "gho_secret"} if seen["token_req"]["code"] == "good" else {"error": "bad_verification_code"})
        assert req.headers["authorization"] == "Bearer gho_secret"
        return httpx.Response(200, json=who)

    monkeypatch.setattr(session, "GITHUB_TRANSPORT", httpx.MockTransport(handler))
    c = TestClient(create_app(), follow_redirects=False)
    c.who, c.seen = who, seen
    return c


def sign_in(c, login="alice"):
    c.who.update(login=login)
    r = c.get("/api/auth/github/login")
    state = parse_qs(urlparse(r.headers["location"]).query)["state"][0]
    return c.get("/api/auth/github/callback", params={"code": "good", "state": state})


def test_login_redirects_to_github_with_state_and_exact_callback(gh):
    r = gh.get("/api/auth/github/login")
    q = parse_qs(urlparse(r.headers["location"]).query)
    assert r.status_code == 302 and r.headers["location"].startswith("https://github.com/login/oauth/authorize")
    assert q["client_id"] == ["cid123"] and q["redirect_uri"] == ["http://localhost:8000/api/auth/github/callback"] and q["scope"] == ["read:user"]
    assert "httponly" in r.headers["set-cookie"].lower() and q["state"][0] in r.headers["set-cookie"]


def test_no_session_means_401_but_signin_endpoints_are_open(gh):
    assert gh.get("/api/contracts").status_code == 401
    assert gh.get("/api/auth/config").json() == {"mode": "apikey", "github": True}
    assert gh.get("/api/auth/me").status_code == 401
    assert gh.get("/api/health").status_code == 200


def test_allowed_user_gets_a_session_and_the_token_is_not_kept(gh):
    r = sign_in(gh)
    assert r.status_code == 302 and r.headers["location"] == "/app"
    assert "gho_secret" not in r.headers["set-cookie"] and "httponly" in r.headers["set-cookie"].lower()
    me = gh.get("/api/auth/me").json()
    assert me["authenticated"] and me["name"] == "Alice A" and me["roles"] == ["Spa.Reviewer"]
    assert gh.get("/api/contracts").status_code == 200
    assert gh.seen["token_req"]["client_secret"] == "csecret"


def test_state_mismatch_and_missing_state_are_rejected(gh):
    gh.get("/api/auth/github/login")
    assert gh.get("/api/auth/github/callback", params={"code": "good", "state": "forged"}).status_code == 400
    fresh = TestClient(create_app(), follow_redirects=False)                      # no state cookie at all
    assert fresh.get("/api/auth/github/callback", params={"code": "good", "state": "x"}).status_code == 400


def test_bad_code_and_user_not_on_allow_list(gh):
    gh.get("/api/auth/github/login")
    state = gh.cookies.get(session.STATE_COOKIE)
    assert gh.get("/api/auth/github/callback", params={"code": "wrong", "state": state}).status_code == 502
    r = sign_in(gh, "stranger")
    assert r.status_code == 403 and "not allowed" in r.text and gh.get("/api/contracts").status_code == 401
    assert session.users() == {"alice": "Spa.Reviewer", "bob": "Spa.Staff"}        # the unknown role 'Spa.Admin' was ignored
    assert sign_in(gh, "evil").status_code == 403


def test_csrf_header_required_for_changes_and_roles_enforced(gh):
    cid = sid("sample_a.pdf")
    sign_in(gh, "alice")
    body = {"action": "accept"}
    assert gh.post(f"/api/contracts/{cid}/fields/price/review", json=body).status_code == 403              # no X-Requested-With
    ok = gh.post(f"/api/contracts/{cid}/fields/price/review", json=body, headers={"X-Requested-With": "spa", "Origin": "https://evil.example"})
    assert ok.status_code == 200
    assert gh.get(f"/api/contracts/{cid}/reviews").json()["decisions"][0]["reviewer"] == "Alice A"        # verified identity
    sign_in(gh, "bob")                                                                                      # staff only
    assert gh.get(f"/api/contracts/{cid}").status_code == 200
    assert gh.post(f"/api/contracts/{cid}/fields/price/review", json=body, headers={"X-Requested-With": "spa"}).status_code == 403
    assert gh.post(f"/api/contracts/{cid}/penalty", json={}, headers={"X-Requested-With": "spa"}).status_code == 200


def test_tampered_expired_and_removed_users_lose_access(gh, monkeypatch):
    sign_in(gh)
    good = gh.cookies.get(session.COOKIE)
    gh.cookies.clear()                                         # from here on, send each cookie explicitly

    def get(token):
        return gh.get("/api/contracts", headers={"Cookie": f"{session.COOKIE}={token}"}).status_code
    assert get(good) == 200
    assert get(good[:-3] + "xyz") == 401                                                                    # bad signature
    exp = lambda **k: jwt.encode({"sub": "github:1", "login": "alice", "name": "A", "role": "Spa.Reviewer", **k}, SECRET, algorithm="HS256")  # noqa: E731
    assert get(exp(exp=int(time.time()) - 5)) == 401                                                        # expired
    assert get(jwt.encode({"sub": "github:1", "login": "alice", "role": "Spa.Reviewer", "exp": int(time.time()) + 999}, "other-secret-" * 4, algorithm="HS256")) == 401   # other secret
    assert get(jwt.encode({"sub": "github:1", "login": "alice", "role": "Spa.Reviewer", "exp": int(time.time()) + 999}, None, algorithm="none")) == 401              # alg none
    assert get(exp(exp=int(time.time()) + 999, role="Spa.Staff")) == 401                                    # role no longer matches the allow-list
    monkeypatch.setenv("GITHUB_USERS", "bob:Spa.Staff")                                                     # alice removed: effective at once
    assert get(good) == 401


def test_logout_and_api_keys_still_work_for_machines(gh):
    sign_in(gh)
    assert gh.post("/api/auth/logout").status_code == 200
    gh.cookies.clear()
    assert gh.get("/api/contracts").status_code == 401
    assert gh.get("/api/contracts", headers={"X-API-Key": KEY}).status_code == 200
    assert gh.get("/api/contracts", headers={"X-API-Key": "wrong-wrong-wrong-wrong-wrong"}).status_code == 401


def test_half_configured_signin_refuses_to_start(env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("GITHUB_CLIENT_ID", "cid")
    for missing, setting in (("GITHUB_CLIENT_SECRET", None), ("PUBLIC_BASE_URL", None)):
        monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match="GITHUB_CLIENT_SECRET"):
        create_app()
    monkeypatch.setenv("GITHUB_CLIENT_SECRET", "x"); monkeypatch.setenv("PUBLIC_BASE_URL", "https://x.example")
    monkeypatch.setenv("SESSION_SECRET", "short"); monkeypatch.setenv("GITHUB_USERS", "a:Spa.Staff")
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()
    monkeypatch.setenv("SESSION_SECRET", "s" * 40); monkeypatch.setenv("GITHUB_USERS", "")
    with pytest.raises(RuntimeError, match="GITHUB_USERS"):
        create_app()
    monkeypatch.setenv("GITHUB_USERS", "a:Spa.Staff"); monkeypatch.setenv("PUBLIC_BASE_URL", "http://example.com")
    with pytest.raises(RuntimeError, match="https"):
        create_app()


def test_github_login_404_when_not_configured(env, monkeypatch):
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    monkeypatch.delenv("AUTH_MODE", raising=False)
    c = TestClient(create_app(), follow_redirects=False)
    assert c.get("/api/auth/github/login").status_code == 404
    assert c.get("/api/auth/me").json()["authenticated"] is False                 # auth off: the UI needs no gate
