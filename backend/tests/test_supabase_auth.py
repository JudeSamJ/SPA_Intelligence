"""Supabase Auth + RBAC. Supabase's Auth API is a mock HTTP transport; the user/role database is a REAL PostgreSQL."""
import json
import logging

import httpx
import jwt
import pytest
from fastapi.testclient import TestClient

from app import buyers, users
from backend.api import persistence, session, supabase_auth
from backend.api.main import create_app
from backend.api.routes import supabase_auth as sb_routes
from backend.tests.test_api import env, seeded, sid  # noqa: F401
from backend.tests.test_database import TEST_URL, pg, q  # noqa: F401
from backend.tests.test_database import pytestmark  # noqa: F401

A, D = sid("sample_a.pdf"), sid("sample_d_rera.pdf")
SECRET = "s" * 40
CHAN = "channel-key-" + "d" * 20
H = {"X-Requested-With": "spa"}


class FakeGoTrue:
    """Just enough of Supabase Auth: password sign-in, sign-up, recover and password update."""

    def __init__(self):
        self.users = {}          # email -> {id, password, confirmed}
        self.calls = []
        self.recovered = []
        self.rate_limit = False

    def add(self, email, password="correct-horse-battery", confirmed=True, uid=None):
        self.users[email] = {"id": uid or f"00000000-0000-0000-0000-{len(self.users) + 1:012d}", "password": password, "confirmed": confirmed}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content or b"{}")
        path = request.url.path.removeprefix("/auth/v1/")
        self.calls.append((request.method, path, dict(request.url.params), request.headers.get("authorization", "")))
        if self.rate_limit:
            return httpx.Response(429, json={"error_code": "over_request_rate_limit"})
        if path == "token":
            u = self.users.get(body.get("email"))
            if not u or u["password"] != body.get("password"):
                return httpx.Response(400, json={"error_code": "invalid_credentials", "msg": "Invalid login credentials"})
            if not u["confirmed"]:
                return httpx.Response(400, json={"error_code": "email_not_confirmed"})
            return httpx.Response(200, json={"access_token": "x", "user": {"id": u["id"], "email": body["email"],
                                                                            "email_confirmed_at": "2026-01-01T00:00:00Z",
                                                                            "user_metadata": {"full_name": "Test Person"}}})
        if path == "signup":
            self.users.setdefault(body["email"], {"id": "11111111-1111-1111-1111-111111111111", "password": body["password"], "confirmed": False})
            return httpx.Response(200, json={"id": "x"})
        if path == "recover":
            self.recovered.append(body["email"])
            return httpx.Response(200, json={})
        if path == "user" and request.method == "PUT":
            if request.headers.get("authorization") != "Bearer good-recovery-token":
                return httpx.Response(401, json={"error_code": "bad_jwt"})
            return httpx.Response(200, json={"id": "x"})
        return httpx.Response(404, json={})


@pytest.fixture
def gt(monkeypatch):
    g = FakeGoTrue()
    monkeypatch.setattr(supabase_auth, "TRANSPORT", httpx.MockTransport(g))
    return g


@pytest.fixture
def app_(env, seeded, pg, gt, monkeypatch, tmp_path):                      # noqa: F811
    monkeypatch.setenv("AUTH_MODE", "supabase")
    monkeypatch.setenv("SUPABASE_URL", "https://proj.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "anon-public-key-123456")
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://localhost:8000")
    monkeypatch.setenv("ADMIN_EMAILS", "boss@company.com")
    monkeypatch.setenv("API_KEYS", json.dumps({CHAN: {"name": "Teams agent", "roles": ["Spa.Channel"]}}))
    monkeypatch.setenv("SPA_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("SPA_NOTIFY_STATE", str(tmp_path / "notified.json"))
    sb_routes.limiter.hits.clear()
    users.clear_cache()
    gt.add("boss@company.com")
    gt.add("rita@company.com")
    gt.add("sam@company.com")
    gt.add("bella@buyer.com")
    with TestClient(create_app()) as c:
        yield c


def client_for(app_, email, password="correct-horse-battery"):
    """A fresh browser session for this user."""
    c = TestClient(app_.app)
    r = c.post("/api/auth/supabase/login", json={"email": email, "password": password}, headers=H)
    assert r.status_code == 200, r.text
    return c


def me(c):
    return c.get("/api/auth/me").json()


# ------------------------------------------------------------------ sign-in
def test_new_user_signs_in_but_is_pending_with_no_access(app_):
    c = client_for(app_, "rita@company.com")
    m = me(c)
    assert m["authenticated"] and m["pending"] is True and m["roles"] == [] and m["login"] == "rita@company.com"
    assert c.get("/api/contracts").status_code == 403                    # signed in, but no role yet
    assert c.get("/api/users").status_code == 403
    assert q("select role from app_users where email = 'rita@company.com'") == [(None,)]


def test_admin_from_env_has_reviewer_and_admin_roles(app_):
    c = client_for(app_, "boss@company.com")
    assert set(me(c)["roles"]) == {"Spa.Reviewer", "Spa.Admin"} and me(c)["pending"] is False
    assert c.get("/api/contracts").status_code == 200
    assert c.get("/api/users", headers=H).status_code == 200


def test_wrong_password_and_unknown_user_look_identical_and_set_no_cookie(app_):
    a = app_.post("/api/auth/supabase/login", json={"email": "rita@company.com", "password": "wrong-wrong-wrong"}, headers=H)
    b = app_.post("/api/auth/supabase/login", json={"email": "nobody@company.com", "password": "wrong-wrong-wrong"}, headers=H)
    assert a.status_code == b.status_code == 401 and a.json() == b.json()
    assert "set-cookie" not in a.headers and "set-cookie" not in b.headers


def test_unconfirmed_email_cannot_sign_in(app_, gt):
    gt.add("new@company.com", confirmed=False)
    r = app_.post("/api/auth/supabase/login", json={"email": "new@company.com", "password": "correct-horse-battery"}, headers=H)
    assert r.status_code == 401 and r.json()["error"]["code"] == "unconfirmed" and "set-cookie" not in r.headers


def test_login_requires_the_csrf_header_and_validates_input(app_):
    ok = {"email": "rita@company.com", "password": "correct-horse-battery"}
    assert app_.post("/api/auth/supabase/login", json=ok).status_code == 403
    assert app_.post("/api/auth/supabase/login", json={"email": "not-an-email", "password": "x"}, headers=H).status_code == 422
    assert app_.post("/api/auth/supabase/login", json={"email": "a@b.co"}, headers=H).status_code == 422


def test_login_is_rate_limited(app_):
    bad = {"email": "rita@company.com", "password": "wrong-wrong-wrong"}
    codes = [app_.post("/api/auth/supabase/login", json=bad, headers=H).status_code for _ in range(11)]
    assert codes[:10] == [401] * 10 and codes[10] == 429


def test_passwords_never_reach_the_logs(app_, caplog):
    with caplog.at_level(logging.DEBUG):
        app_.post("/api/auth/supabase/login", json={"email": "rita@company.com", "password": "Sup3r-secret-pass!"}, headers=H)
        app_.post("/api/auth/supabase/signup", json={"email": "x@company.com", "password": "Sup3r-secret-pass!"}, headers=H)
    assert "Sup3r-secret-pass" not in caplog.text


def test_signup_gives_the_same_answer_for_new_and_existing_addresses(app_):
    new = app_.post("/api/auth/supabase/signup", json={"email": "fresh@company.com", "password": "a-long-enough-pass"}, headers=H)
    old = app_.post("/api/auth/supabase/signup", json={"email": "rita@company.com", "password": "a-long-enough-pass"}, headers=H)
    assert new.status_code == old.status_code == 202 and new.json() == old.json() == {"check_email": True}
    assert app_.post("/api/auth/supabase/signup", json={"email": "f@company.com", "password": "short"}, headers=H).status_code == 422


def test_signup_asks_supabase_to_redirect_back_to_our_login(app_, gt):
    app_.post("/api/auth/supabase/signup", json={"email": "fresh@company.com", "password": "a-long-enough-pass"}, headers=H)
    redirect = [c[2] for c in gt.calls if c[1] == "signup"][0]["redirect_to"]
    assert redirect == "http://localhost:8000/login?confirmed=1"


def test_recover_never_reveals_whether_an_account_exists(app_, gt):
    for e in ("rita@company.com", "ghost@company.com"):
        r = app_.post("/api/auth/supabase/recover", json={"email": e}, headers=H)
        assert r.status_code == 202 and r.json() == {"check_email": True}
    gt.rate_limit = True
    assert app_.post("/api/auth/supabase/recover", json={"email": "rita@company.com"}, headers=H).status_code == 429


def test_password_reset_uses_the_recovery_token_once_over_the_api(app_, gt):
    ok = app_.post("/api/auth/supabase/reset", json={"token": "good-recovery-token", "password": "a-brand-new-password"}, headers=H)
    assert ok.status_code == 200
    assert [c for c in gt.calls if c[1] == "user"][0][3] == "Bearer good-recovery-token"
    assert app_.post("/api/auth/supabase/reset", json={"token": "expired-token-value", "password": "a-brand-new-password"}, headers=H).status_code == 401
    assert app_.post("/api/auth/supabase/reset", json={"token": "good-recovery-token", "password": "short"}, headers=H).status_code == 422


def test_new_style_publishable_keys_go_in_the_apikey_header_only(app_, gt, monkeypatch):
    monkeypatch.setenv("SUPABASE_ANON_KEY", "sb_publishable_abc123")
    app_.post("/api/auth/supabase/login", json={"email": "rita@company.com", "password": "correct-horse-battery"}, headers=H)
    assert gt.calls[-1][3] == ""                                           # no Authorization header with a non-JWT key
    monkeypatch.setenv("SUPABASE_ANON_KEY", "eyJlegacy.jwt.anon")
    app_.post("/api/auth/supabase/login", json={"email": "rita@company.com", "password": "correct-horse-battery"}, headers=H)
    assert gt.calls[-1][3] == "Bearer eyJlegacy.jwt.anon"


# ------------------------------------------------------------------ RBAC
def test_admin_assigns_roles_and_they_take_effect_immediately(app_):
    admin, rita, sam = client_for(app_, "boss@company.com"), client_for(app_, "rita@company.com"), client_for(app_, "sam@company.com")
    ids = {u["email"]: u["user_id"] for u in admin.get("/api/users").json()["users"]}
    assert admin.get("/api/users").json()["users"][0]["role"] is None                       # pending users are listed first
    assert admin.put(f"/api/users/{ids['sam@company.com']}/role", json={"role": "staff"}, headers=H).status_code == 200
    assert admin.put(f"/api/users/{ids['rita@company.com']}/role", json={"role": "reviewer"}, headers=H).status_code == 200
    # staff: read yes, change no
    assert sam.get("/api/contracts").status_code == 200
    assert sam.post("/api/buyers", json={"contract_id": A, "identity": "a@b.co"}, headers=H).status_code == 403
    assert sam.get("/api/users").status_code == 403
    # reviewer: read and change, but not user management
    assert rita.get("/api/contracts").status_code == 200
    assert rita.post("/api/buyers", json={"contract_id": A, "identity": "a@b.co"}, headers=H).status_code == 201
    assert rita.get("/api/users").status_code == 403
    assert rita.put(f"/api/users/{ids['sam@company.com']}/role", json={"role": "reviewer"}, headers=H).status_code == 403
    # removing a role cuts access on the very next request, with the same cookie
    admin.put(f"/api/users/{ids['rita@company.com']}/role", json={"role": None}, headers=H)
    assert rita.get("/api/contracts").status_code == 403


def test_role_changes_validate_input(app_):
    admin = client_for(app_, "boss@company.com")
    uid = admin.get("/api/users").json()["users"][0]["user_id"]
    assert admin.put(f"/api/users/{uid}/role", json={"role": "superuser"}, headers=H).status_code == 422
    assert admin.put(f"/api/users/{uid}/role", json={"role": "admin"}, headers=H).status_code == 422      # admin is env-only, never a row
    assert admin.put("/api/users/does-not-exist/role", json={"role": "staff"}, headers=H).status_code == 404


def test_buyer_is_recognised_by_a_confirmed_email_with_an_assignment(app_):
    rita_admin = client_for(app_, "boss@company.com")
    assert rita_admin.post("/api/buyers", json={"contract_id": A, "identity": "Bella@Buyer.com"}, headers=H).status_code == 201
    bella = client_for(app_, "bella@buyer.com")
    assert set(me(bella)["roles"]) == {"Spa.Buyer"} and me(bella)["pending"] is False
    assert bella.get("/api/buyer/me").json() == {"linked": True, "contract_name": "sample_a.pdf"}
    r = bella.post("/api/buyer/chat", json={"message": "Can I cancel and get a refund?"}, headers=H)
    assert r.status_code == 200 and r.json()["reason"] == "legal_advice"
    # a buyer sees nothing else
    for path in ("/api/contracts", "/api/users", "/api/buyers", "/api/review-queue"):
        assert bella.get(path).status_code == 403, path
    assert bella.post("/api/buyers", json={"contract_id": D, "identity": "bella@buyer.com"}, headers=H).status_code == 403


def test_a_buyer_without_an_assignment_gets_no_access_and_unlinking_cuts_it(app_):
    admin = client_for(app_, "boss@company.com")
    bella = client_for(app_, "bella@buyer.com")
    assert me(bella)["pending"] is True and bella.get("/api/buyer/me").json()["linked"] is False
    assert bella.post("/api/buyer/chat", json={"message": "hi"}, headers=H).status_code == 403
    row = admin.post("/api/buyers", json={"contract_id": A, "identity": "bella@buyer.com"}, headers=H).json()
    users.clear_cache()
    assert bella.get("/api/buyer/me").json()["linked"] is True
    admin.delete(f"/api/buyers/{row['id']}", headers=H)
    users.clear_cache()
    assert bella.post("/api/buyer/chat", json={"message": "hi"}, headers=H).status_code == 403


def test_user_list_marks_buyers_who_have_access_only_through_a_link(app_):
    admin = client_for(app_, "boss@company.com")
    client_for(app_, "bella@buyer.com")
    client_for(app_, "rita@company.com")
    admin.post("/api/buyers", json={"contract_id": A, "identity": "bella@buyer.com"}, headers=H)
    rows = {u["email"]: u for u in admin.get("/api/users").json()["users"]}
    assert rows["bella@buyer.com"]["via_assignment"] is True and rows["bella@buyer.com"]["role"] is None
    assert rows["rita@company.com"]["via_assignment"] is False and rows["rita@company.com"]["role"] is None


def test_two_buyers_never_see_each_others_contract(app_, gt):
    gt.add("dan@buyer.com")
    admin = client_for(app_, "boss@company.com")
    admin.post("/api/buyers", json={"contract_id": A, "identity": "bella@buyer.com"}, headers=H)
    admin.post("/api/buyers", json={"contract_id": D, "identity": "dan@buyer.com"}, headers=H)
    assert client_for(app_, "bella@buyer.com").get("/api/buyer/me").json()["contract_name"] == "sample_a.pdf"
    assert client_for(app_, "dan@buyer.com").get("/api/buyer/me").json()["contract_name"] == "sample_d_rera.pdf"


def test_an_explicit_role_overrides_the_buyer_assignment(app_):
    admin = client_for(app_, "boss@company.com")
    admin.post("/api/buyers", json={"contract_id": A, "identity": "sam@company.com"}, headers=H)
    sam = client_for(app_, "sam@company.com")
    assert set(me(sam)["roles"]) == {"Spa.Buyer"}
    uid = [u for u in admin.get("/api/users").json()["users"] if u["email"] == "sam@company.com"][0]["user_id"]
    admin.put(f"/api/users/{uid}/role", json={"role": "staff"}, headers=H)
    assert set(me(sam)["roles"]) == {"Spa.Staff"}


# ------------------------------------------------------------------ cookies and keys
def test_forged_and_malformed_cookies_are_refused(app_):
    now = 4_000_000_000
    forged = jwt.encode({"sub": "sb:x", "email": "boss@company.com", "prov": "supabase", "exp": now}, "wrong-secret-wrong-secret-wrong!!", algorithm="HS256")
    for tok in (forged, "garbage", ""):
        c = TestClient(app_.app)
        c.cookies.set(session.COOKIE, tok)
        assert c.get("/api/contracts").status_code == 401
        assert me(c)["authenticated"] is False
    # a GitHub-style cookie (role claim, no provider) is not accepted when its login is not on the allow-list
    gh = jwt.encode({"sub": "github:1", "login": "evil", "role": "Spa.Reviewer", "exp": now}, SECRET, algorithm="HS256")
    c = TestClient(app_.app)
    c.cookies.set(session.COOKIE, gh)
    assert c.get("/api/contracts").status_code == 401


def test_session_for_a_user_whose_row_was_deleted_still_gets_no_role(app_):
    rita = client_for(app_, "rita@company.com")
    q("delete from app_users")
    users.clear_cache()
    assert rita.get("/api/contracts").status_code == 403


def test_channel_api_keys_still_work_in_supabase_mode(app_):
    admin = client_for(app_, "boss@company.com")
    admin.post("/api/buyers", json={"contract_id": A, "identity": "+971501234567", "channel": "whatsapp"}, headers=H)
    r = app_.post("/api/buyer/chat", json={"message": "Can I cancel and get a refund?", "channel": "whatsapp"},
                  headers={"X-API-Key": CHAN, "X-Buyer-Identity": "+971501234567"})
    assert r.status_code == 200 and r.json()["reason"] == "legal_advice"
    assert app_.get("/api/contracts", headers={"X-API-Key": CHAN}).status_code == 403


def test_logout_clears_the_session(app_):
    c = client_for(app_, "boss@company.com")
    assert c.get("/api/contracts").status_code == 200
    c.post("/api/auth/logout", headers=H)
    assert c.get("/api/contracts").status_code == 401


def test_health_works_in_supabase_mode_and_reports_the_database(app_):
    """Regression: the response schema once rejected auth_mode 'supabase', so /api/health returned 500 on a deployed server."""
    r = app_.get("/api/health")
    assert r.status_code == 200
    h = r.json()
    assert h["auth_mode"] == "supabase" and h["status"] == "ok" and h["database"]["enabled"] is True


@pytest.mark.parametrize("mode", ["off", "apikey", "supabase"])
def test_health_answers_for_every_auth_mode(env, pg, monkeypatch, mode):
    monkeypatch.setenv("AUTH_MODE", mode)
    for k, v in {"SUPABASE_URL": "https://p.supabase.co", "SUPABASE_ANON_KEY": "anon-public-key-123456", "SESSION_SECRET": SECRET,
                 "PUBLIC_BASE_URL": "http://localhost:8000", "ADMIN_EMAILS": "a@b.co",
                 "API_KEYS": json.dumps({CHAN: {"name": "k", "roles": ["Spa.Channel"]}})}.items():
        monkeypatch.setenv(k, v)
    with TestClient(create_app()) as c:
        r = c.get("/api/health")
        assert r.status_code == 200 and r.json()["auth_mode"] == mode


def test_config_endpoint_reports_email_sign_in(app_):
    cfg = app_.get("/api/auth/config").json()
    assert cfg["mode"] == "supabase" and cfg["email"] is True


def test_database_outage_during_sign_in_is_a_clear_503_not_a_crash(app_, monkeypatch):
    monkeypatch.setattr(users, "touch", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("db down")))
    r = app_.post("/api/auth/supabase/login", json={"email": "rita@company.com", "password": "correct-horse-battery"}, headers=H)
    assert r.status_code == 503 and r.json()["error"]["code"] == "database_unavailable" and "set-cookie" not in r.headers


# ------------------------------------------------------------------ fail closed
@pytest.mark.parametrize("missing", ["SUPABASE_URL", "SUPABASE_ANON_KEY", "PUBLIC_BASE_URL", "ADMIN_EMAILS", "DATABASE_URL"])
def test_supabase_mode_refuses_to_start_when_misconfigured(env, pg, monkeypatch, missing):
    for k, v in {"AUTH_MODE": "supabase", "SUPABASE_URL": "https://p.supabase.co", "SUPABASE_ANON_KEY": "anon-public-key-123456",
                 "SESSION_SECRET": SECRET, "PUBLIC_BASE_URL": "https://app.example.com", "ADMIN_EMAILS": "a@b.co"}.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(RuntimeError, match=missing):
        create_app()


def test_supabase_mode_needs_a_long_session_secret_and_https(env, pg, monkeypatch):
    for k, v in {"AUTH_MODE": "supabase", "SUPABASE_URL": "https://p.supabase.co", "SUPABASE_ANON_KEY": "anon-public-key-123456",
                 "SESSION_SECRET": "short", "PUBLIC_BASE_URL": "https://app.example.com", "ADMIN_EMAILS": "a@b.co"}.items():
        monkeypatch.setenv(k, v)
    with pytest.raises(RuntimeError, match="SESSION_SECRET"):
        create_app()
    monkeypatch.setenv("SESSION_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://insecure.example.com")
    with pytest.raises(RuntimeError, match="https"):
        create_app()
