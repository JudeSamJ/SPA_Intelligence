"""Buyer assignments through the real database: one channel key serves every buyer; the contract comes from the table."""
import json

import pytest
from fastapi.testclient import TestClient

from app import buyers, db
from backend.api import persistence
from backend.api.main import create_app
from backend.tests.test_api import env, seeded, sid  # noqa: F401
from backend.tests.test_database import TEST_URL, pg, q  # noqa: F401  (pg fixture + skip marker)
from backend.tests.test_database import pytestmark  # noqa: F401

REV, STAFF, CHAN = "reviewer-key-" + "b" * 20, "staff-key-" + "a" * 20, "channel-key-" + "d" * 20


@pytest.fixture
def api(env, seeded, pg, monkeypatch, tmp_path):
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("API_KEYS", json.dumps({
        STAFF: {"name": "Staff", "roles": ["Spa.Staff"]},
        REV: {"name": "Rita Reviewer", "roles": ["Spa.Reviewer"]},
        CHAN: {"name": "Teams agent", "roles": ["Spa.Channel"]}}))
    monkeypatch.setenv("SPA_AUDIT_DIR", str(tmp_path / "audit"))
    monkeypatch.setenv("SPA_NOTIFY_STATE", str(tmp_path / "notified.json"))
    with TestClient(create_app()) as c:
        yield c


H = lambda k, **x: {"X-API-Key": k, **x}  # noqa: E731
A, D = sid("sample_a.pdf"), sid("sample_d_rera.pdf")


def test_identity_normalisation():
    assert buyers.normalize_identity("  Jude.Sam@Example.COM ") == "jude.sam@example.com"
    assert buyers.normalize_identity("+971 50-123 4567") == "+971501234567"
    for bad in ("", "nope", "12", "a@b", "x" * 40):
        with pytest.raises(buyers.BuyerError):
            buyers.normalize_identity(bad)


def test_staff_can_read_only_reviewer_can_change(api):
    body = {"contract_id": A, "identity": "buyer@example.com"}
    assert api.post("/api/buyers", json=body, headers=H(STAFF)).status_code == 403
    r = api.post("/api/buyers", json=body, headers=H(REV))
    assert r.status_code == 201 and r.json()["created_by"] == "Rita Reviewer"
    listed = api.get("/api/buyers", headers=H(STAFF)).json()["assignments"]
    assert [x["identity"] for x in listed] == ["buyer@example.com"]
    assert api.delete(f"/api/buyers/{r.json()['id']}", headers=H(STAFF)).status_code == 403
    assert api.delete(f"/api/buyers/{r.json()['id']}", headers=H(REV)).status_code == 200
    assert api.get("/api/buyers", headers=H(STAFF)).json()["assignments"] == []
    assert api.delete("/api/buyers/999999", headers=H(REV)).status_code == 404


def test_validation_and_conflicts(api):
    assert api.post("/api/buyers", json={"contract_id": A, "identity": "not valid"}, headers=H(REV)).status_code == 422
    assert api.post("/api/buyers", json={"contract_id": "0" * 64, "identity": "a@b.co"}, headers=H(REV)).status_code == 404
    assert api.post("/api/buyers", json={"contract_id": A, "identity": "a@b.co", "channel": "fax"}, headers=H(REV)).status_code == 422
    ok = {"contract_id": A, "identity": "a@b.co"}
    assert api.post("/api/buyers", json=ok, headers=H(REV)).status_code == 201
    assert api.post("/api/buyers", json=ok, headers=H(REV)).status_code == 201            # same assignment again: no duplicate
    assert len(api.get("/api/buyers", headers=H(STAFF)).json()["assignments"]) == 1
    other = api.post("/api/buyers", json={"contract_id": D, "identity": "A@B.co"}, headers=H(REV))
    assert other.status_code == 409                                                       # one buyer, one contract


def test_channel_key_answers_only_for_the_assigned_contract(api):
    api.post("/api/buyers", json={"contract_id": A, "identity": "+971 50 123 4567", "channel": "whatsapp"}, headers=H(REV))
    ask = {"message": "Can I cancel and get a refund?", "channel": "whatsapp"}
    ok = api.post("/api/buyer/chat", json=ask, headers=H(CHAN, **{"X-Buyer-Identity": "+971501234567"}))
    assert ok.status_code == 200 and ok.json()["reason"] == "legal_advice"                # answered from contract A, refused as advice
    # an unknown buyer, a missing identity, the wrong channel, a staff key and no key are all refused
    assert api.post("/api/buyer/chat", json=ask, headers=H(CHAN, **{"X-Buyer-Identity": "+971509999999"})).status_code == 403
    assert api.post("/api/buyer/chat", json=ask, headers=H(CHAN)).status_code == 403
    assert api.post("/api/buyer/chat", json={**ask, "channel": "teams"},
                    headers=H(CHAN, **{"X-Buyer-Identity": "+971501234567"})).status_code == 403
    assert api.post("/api/buyer/chat", json=ask, headers=H(STAFF, **{"X-Buyer-Identity": "+971501234567"})).status_code == 403
    assert api.post("/api/buyer/chat", json=ask).status_code == 401
    # the channel key can do nothing else
    assert api.get("/api/contracts", headers=H(CHAN)).status_code == 403
    assert api.get("/api/buyers", headers=H(CHAN)).status_code == 403


def test_removing_an_assignment_cuts_access_immediately(api):
    r = api.post("/api/buyers", json={"contract_id": A, "identity": "x@y.co"}, headers=H(REV)).json()
    ask = {"message": "Can I cancel and get a refund?"}
    hdr = H(CHAN, **{"X-Buyer-Identity": "x@y.co"})
    assert api.post("/api/buyer/chat", json=ask, headers=hdr).status_code == 200
    api.delete(f"/api/buyers/{r['id']}", headers=H(REV))
    assert api.post("/api/buyer/chat", json=ask, headers=hdr).status_code == 403


def test_two_contracts_for_one_identity_is_ambiguous_so_refused(api):
    q("insert into buyer_assignments (contract_id, identity, channel) values (%s,'z@y.co','teams'), (%s,'z@y.co','any')", (A, D))
    assert buyers.contract_for_identity("z@y.co", "teams") is None


def test_audit_rows_land_in_the_database_without_identities(api):
    api.post("/api/buyers", json={"contract_id": A, "identity": "pii@example.com"}, headers=H(REV))
    api.post("/api/buyer/chat", json={"message": "Can I cancel and get a refund?", "channel": "teams"},
             headers=H(CHAN, **{"X-Buyer-Identity": "pii@example.com"}))
    rows = q("select buyer, contract_id, channel, refused, reason from audit_log")
    assert len(rows) == 1 and rows[0][1] == A and rows[0][2] == "teams" and rows[0][3] is True and rows[0][4] == "legal_advice"
    assert "pii@example.com" not in rows[0][0]                                            # hashed, not stored in clear


def test_assignments_need_a_database(env, seeded, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("API_KEYS", json.dumps({REV: {"name": "R", "roles": ["Spa.Reviewer"]}}))
    with TestClient(create_app()) as c:
        r = c.post("/api/buyers", json={"contract_id": A, "identity": "a@b.co"}, headers=H(REV))
        assert r.status_code == 422 and "DATABASE_URL" in r.json()["error"]["message"]
