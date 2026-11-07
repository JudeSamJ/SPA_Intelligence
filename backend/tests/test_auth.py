"""Entra bearer-token auth: tokens are signed with a locally generated RSA key and the key set is injected,
so no network or tenant is needed. Covers signature, audience, issuer/tenant, expiry, roles and buyer scoping."""
import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from jwt.algorithms import RSAAlgorithm

from backend.api import auth
from backend.api.main import create_app
from backend.tests.test_api import env, seeded, sid  # noqa: F401  (fixtures)

TENANT, CLIENT = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwks(*keys):
    out = []
    for kid, k in keys:
        j = json.loads(RSAAlgorithm.to_jwk(k.public_key()))
        j.update(kid=kid, use="sig", alg="RS256")
        out.append(j)
    return {"keys": out}


def token(roles=(), key=KEY, kid="k1", aud=CLIENT, tid=TENANT, iss=None, exp=3600, oid="oid-1", name="Dana Reviewer", alg="RS256"):
    now = int(time.time())
    claims = {"aud": aud, "iss": iss or f"https://login.microsoftonline.com/{tid}/v2.0", "tid": tid, "iat": now,
              "exp": now + exp, "oid": oid, "name": name, "preferred_username": "dana@example.invalid", "roles": list(roles)}
    return jwt.encode(claims, key, algorithm=alg, headers={"kid": kid})


@pytest.fixture
def secure(env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.setenv("ENTRA_TENANT_ID", TENANT)
    monkeypatch.setenv("ENTRA_CLIENT_ID", CLIENT)
    monkeypatch.setattr(auth, "JWKS_FETCHER", lambda tenant: jwks(("k1", KEY)))
    auth.reset_cache()
    yield TestClient(create_app())
    auth.reset_cache()


def H(**kw):
    return {"Authorization": f"Bearer {token(**kw)}"}


def test_health_is_open_and_reports_mode(secure):
    j = secure.get("/api/health").json()
    assert j["auth_mode"] == "entra"


def test_no_token_or_garbage_token_is_401(secure):
    assert secure.get("/api/contracts").status_code == 401
    assert secure.get("/api/contracts", headers={"Authorization": "Bearer not-a-jwt-at-all-xxxxxxxx"}).status_code == 401
    assert secure.get("/api/contracts", headers={"Authorization": "Basic abcdefghijklmnopqrstuvwxyz"}).status_code == 401
    assert secure.get("/api/packs").status_code == 401


@pytest.mark.parametrize("kw,why", [
    ({"exp": -3600}, "expired"),
    ({"aud": "someone-else"}, "wrong audience"),
    ({"tid": "99999999-9999-9999-9999-999999999999"}, "other tenant"),
    ({"iss": "https://evil.example/v2.0"}, "other issuer"),
    ({"key": OTHER}, "signed with a key the tenant does not publish"),
    ({"kid": "unknown-kid"}, "unknown key id"),
])
def test_bad_tokens_rejected(secure, kw, why):
    r = secure.get("/api/contracts", headers=H(roles=["Spa.Reviewer"], **kw))
    assert r.status_code == 401, why


def test_hs256_and_none_algorithm_confusion_rejected(secure):
    now = int(time.time())
    claims = {"aud": CLIENT, "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "tid": TENANT, "exp": now + 600, "roles": ["Spa.Reviewer"]}
    import base64
    import hashlib
    import hmac
    from cryptography.hazmat.primitives import serialization
    pem = KEY.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    b64 = lambda b: base64.urlsafe_b64encode(b).rstrip(b"=")            # noqa: E731
    signing_input = b64(json.dumps({"alg": "HS256", "kid": "k1", "typ": "JWT"}).encode()) + b"." + b64(json.dumps(claims).encode())
    hs = (signing_input + b"." + b64(hmac.new(pem, signing_input, hashlib.sha256).digest())).decode()   # classic RS256->HS256 confusion
    assert secure.get("/api/contracts", headers={"Authorization": f"Bearer {hs}"}).status_code == 401
    none = jwt.encode(claims, None, algorithm="none", headers={"kid": "k1"})
    assert secure.get("/api/contracts", headers={"Authorization": f"Bearer {none}"}).status_code == 401


def test_v1_issuer_and_api_uri_audience_accepted(secure):
    h = H(roles=["Spa.Staff"], aud=f"api://{CLIENT}", iss=f"https://sts.windows.net/{TENANT}/")
    assert secure.get("/api/contracts", headers=h).status_code == 200


def test_roles_staff_reads_reviewer_writes_buyer_nothing(secure, seeded):
    cid = sid("sample_a.pdf")
    staff, rev, buyer = H(roles=["Spa.Staff"]), H(roles=["Spa.Reviewer"]), H(roles=["Spa.Buyer"])
    assert secure.get(f"/api/contracts/{cid}", headers=staff).status_code == 200
    assert secure.get(f"/api/contracts/{cid}", headers=buyer).status_code == 403
    assert secure.get("/api/contracts", headers=H(roles=[])).status_code == 403            # signed in, no role
    # computing POSTs are read-only: Staff may call them
    assert secure.post(f"/api/contracts/{cid}/penalty", json={}, headers=staff).status_code == 200
    # data-changing / LLM-spending POSTs need Reviewer
    body = {"action": "accept"}
    assert secure.post(f"/api/contracts/{cid}/fields/price/review", json=body, headers=staff).status_code == 403
    assert secure.post(f"/api/contracts/{cid}/extract?force=true", headers=staff).status_code == 403
    assert secure.put(f"/api/contracts/{cid}/jurisdiction", json={"jurisdiction": None}, headers=staff).status_code == 403
    assert secure.post("/api/eval/run", json={}, headers=staff).status_code == 403
    assert secure.post(f"/api/contracts/{cid}/erp/push", json={"confirm": True}, headers=staff).status_code == 403
    assert secure.post(f"/api/contracts/{cid}/fields/price/review", json=body, headers=rev).status_code == 200


def test_reviewer_identity_comes_from_the_token_not_the_body(secure, seeded):
    cid = sid("sample_a.pdf")
    secure.post(f"/api/contracts/{cid}/fields/price/review", headers=H(roles=["Spa.Reviewer"], name="Real Person"),
                json={"action": "accept", "reviewer": "Somebody Else"})
    d = secure.get(f"/api/contracts/{cid}/reviews", headers=H(roles=["Spa.Staff"])).json()["decisions"][0]
    assert d["reviewer"] == "Real Person"


def test_signing_key_rollover_refetches_once(secure, monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "JWKS_FETCHER", lambda t: (calls.append(1), jwks(("k1", KEY)) if len(calls) == 1 else jwks(("k1", KEY), ("k2", OTHER)))[1])
    auth.reset_cache()
    assert secure.get("/api/contracts", headers=H(roles=["Spa.Staff"])).status_code == 200
    assert secure.get("/api/contracts", headers=H(roles=["Spa.Staff"], key=OTHER, kid="k2")).status_code == 200
    assert len(calls) == 2


def test_idp_outage_is_503_not_open(secure, monkeypatch):
    import httpx

    def boom(t):
        raise httpx.ConnectError("down")
    monkeypatch.setattr(auth, "JWKS_FETCHER", boom)
    auth.reset_cache()
    assert secure.get("/api/contracts", headers=H(roles=["Spa.Staff"])).status_code == 503


def test_buyer_chat_entra_maps_oid_to_one_contract(secure, seeded, monkeypatch, tmp_path):
    monkeypatch.setenv("SPA_AUDIT_DIR", str(tmp_path / "audit"))
    a = sid("sample_a.pdf")
    monkeypatch.setenv("BUYER_ACCOUNTS", json.dumps({"OID-BUYER-1": a}))
    ok = secure.post("/api/buyer/chat", json={"message": "Can I cancel and get a refund?"}, headers=H(roles=["Spa.Buyer"], oid="oid-buyer-1"))
    assert ok.status_code == 200 and ok.json()["refused"] and ok.json()["reason"] == "legal_advice"
    assert secure.post("/api/buyer/chat", json={"message": "hi"}, headers=H(roles=["Spa.Buyer"], oid="someone-else")).status_code == 403   # not linked
    assert secure.post("/api/buyer/chat", json={"message": "hi"}, headers=H(roles=["Spa.Staff"], oid="oid-buyer-1")).status_code == 403    # wrong role
    assert secure.post("/api/buyer/chat", json={"message": "hi"}).status_code == 401
    log = (tmp_path / "audit" / "buyer_chat.jsonl").read_text()
    assert "oid-buyer-1" not in log and a in log                                    # only a short hash of the identity is logged


def test_buyer_token_stub_ignored_in_entra_mode(secure, seeded, monkeypatch):
    monkeypatch.setenv("BUYER_TOKENS", json.dumps({"tok-buyer-a-123": sid("sample_a.pdf")}))
    assert secure.post("/api/buyer/chat", json={"message": "hi"}, headers={"Authorization": "Bearer tok-buyer-a-123"}).status_code == 401


def test_entra_mode_without_settings_refuses_to_start(env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "entra")
    monkeypatch.delenv("ENTRA_TENANT_ID", raising=False)
    monkeypatch.delenv("ENTRA_CLIENT_ID", raising=False)
    with pytest.raises(RuntimeError, match="ENTRA_TENANT_ID"):
        create_app()
    monkeypatch.setenv("AUTH_MODE", "enra")                       # typo must not silently mean "open"
    with pytest.raises(RuntimeError, match="Unknown AUTH_MODE"):
        create_app()


def test_auth_off_keeps_everything_open(env, seeded, monkeypatch):
    monkeypatch.delenv("AUTH_MODE", raising=False)
    c = TestClient(create_app())
    assert c.get("/api/contracts").status_code == 200


# ------------------------------------------------------------------ AUTH_MODE=apikey (demo mode without Entra registrations)
STAFF_KEY, REV_KEY, BUYER_KEY = "staff-key-" + "a" * 20, "reviewer-key-" + "b" * 20, "buyer-key-" + "c" * 20


@pytest.fixture
def keyed(env, seeded, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("API_KEYS", json.dumps({
        STAFF_KEY: {"name": "Demo staff", "roles": ["Spa.Staff"]},
        REV_KEY: {"name": "Demo reviewer", "roles": ["Spa.Reviewer"]},
        BUYER_KEY: {"name": "Demo buyer", "roles": ["Spa.Buyer"], "contract": sid("sample_a.pdf")},
        "short": {"name": "weak", "roles": ["Spa.Reviewer"]}}))
    return TestClient(create_app())


def test_apikey_requires_a_key_and_ignores_short_keys(keyed):
    assert keyed.get("/api/health").json()["auth_mode"] == "apikey"
    assert keyed.get("/api/contracts").status_code == 401
    assert keyed.get("/api/contracts", headers={"X-API-Key": "wrong-wrong-wrong-wrong-wrong"}).status_code == 401
    assert keyed.get("/api/contracts", headers={"X-API-Key": "short"}).status_code == 401           # too short to be a key
    assert keyed.get("/api/contracts", headers={"Authorization": f"Bearer {STAFF_KEY}"}).status_code == 401   # only the header counts


def test_apikey_role_matrix_and_verified_name(keyed):
    cid = sid("sample_a.pdf")
    s, r = {"X-API-Key": STAFF_KEY}, {"X-API-Key": REV_KEY}
    assert keyed.get(f"/api/contracts/{cid}", headers=s).status_code == 200
    assert keyed.post(f"/api/contracts/{cid}/penalty", json={}, headers=s).status_code == 200
    assert keyed.post(f"/api/contracts/{cid}/fields/price/review", json={"action": "accept"}, headers=s).status_code == 403
    assert keyed.get(f"/api/contracts/{cid}", headers={"X-API-Key": BUYER_KEY}).status_code == 403
    keyed.post(f"/api/contracts/{cid}/fields/price/review", json={"action": "accept", "reviewer": "Forged Name"}, headers=r)
    assert keyed.get(f"/api/contracts/{cid}/reviews", headers=s).json()["decisions"][0]["reviewer"] == "Demo reviewer"


def test_apikey_buyer_is_bound_to_its_contract(keyed, tmp_path, monkeypatch):
    monkeypatch.setenv("SPA_AUDIT_DIR", str(tmp_path / "audit"))
    ok = keyed.post("/api/buyer/chat", json={"message": "Can I cancel and get a refund?"}, headers={"X-API-Key": BUYER_KEY})
    assert ok.status_code == 200 and ok.json()["reason"] == "legal_advice"
    assert keyed.post("/api/buyer/chat", json={"message": "hi"}, headers={"X-API-Key": STAFF_KEY}).status_code == 403
    assert keyed.post("/api/buyer/chat", json={"message": "hi"}).status_code == 401
    log = (tmp_path / "audit" / "buyer_chat.jsonl").read_text()
    assert BUYER_KEY not in log and sid("sample_a.pdf") in log


def test_apikey_mode_without_valid_keys_refuses_to_start(env, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("API_KEYS", json.dumps({"short": {"roles": ["Spa.Staff"]}}))
    with pytest.raises(RuntimeError, match="API_KEYS"):
        create_app()
    monkeypatch.delenv("API_KEYS")
    with pytest.raises(RuntimeError, match="API_KEYS"):
        create_app()
