import csv
import io
import json
from datetime import date
from pathlib import Path

import httpx
import pytest
import yaml

from app.erp import d365
from tests.test_statute_gap import PAID, contract, S  # noqa: F401

FIX = Path(__file__).parent / "fixtures" / "rates"


@pytest.fixture(autouse=True)
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("SPA_RATES_DIR", str(FIX))
    monkeypatch.setenv("SPA_AUDIT_DIR", str(tmp_path / "audit"))
    for k in ("ERP_PUSH_ENABLED", "D365_TENANT_ID", "D365_CLIENT_ID", "D365_CLIENT_SECRET", "D365_RESOURCE"):
        monkeypatch.delenv(k, raising=False)


def make():
    from app.schema import Milestone
    c = contract(plan=[Milestone(name="Booking", percent=40, due_date=date(2024, 6, 1), source_page=2, source_quote="x"),
                       Milestone(name="Later", percent=60, due_date=date(2026, 1, 1), source_page=2, source_quote="y")])
    c.currency, c.jurisdiction = "INR", "in_rera"
    return c


def test_dry_run_rows_and_csv():
    r = d365.export(make(), "id", "n", 100, date(2025, 1, 1))
    assert r["mode"] == "dry_run" and r["valid"] and r["placeholder_mapping"]
    lines = {row["TODO_LineType"]: [] for row in r["rows"]}
    assert r["row_count"] == 4          # 2 payments + contractual + statutory exposure
    pay = [x for x in r["rows"] if x["TODO_LineType"] == "payment"]
    assert [p["TODO_Amount"] for p in pay] == [400000.0, 600000.0] and pay[0]["TODO_DueDate"] == "2024-06-01"
    exp = [x for x in r["rows"] if x["TODO_LineType"] == "exposure"]
    assert exp[0]["TODO_Amount"] == 11506.85                        # contractual, same as the deterministic simulator
    assert "unreviewed legal logic" in exp[1]["TODO_Description"]
    rows = list(csv.DictReader(io.StringIO(r["csv"])))
    assert rows[0]["TODO_CurrencyCode"] == "INR" and len(rows) == 4
    assert "PLACEHOLDERS" in r["mapping_note"]


def test_validation_errors_reported_not_guessed():
    c = make()
    c.payment_plan[0].due_date = None
    c.currency = "INRX"
    r = d365.export(c, "id", "n", None, date(2025, 1, 1))
    assert not r["valid"]
    msgs = {(e["row"], e["source"], e["error"]) for e in r["errors"]}
    assert (1, "due_date", "required value is missing") in msgs
    assert any(e["source"] == "currency" and "longer than 3" in e["error"] for e in r["errors"])


def test_push_disabled_by_default_and_needs_confirm_and_blocks_placeholders(monkeypatch):
    with pytest.raises(d365.PushError, match="disabled"):
        d365.push(make(), "id", "n", None, date(2025, 1, 1), confirm=True)
    monkeypatch.setenv("ERP_PUSH_ENABLED", "1")
    with pytest.raises(d365.PushError, match="confirmation"):
        d365.push(make(), "id", "n", None, date(2025, 1, 1), confirm=False)
    with pytest.raises(d365.PushError, match="placeholder"):
        d365.push(make(), "id", "n", None, date(2025, 1, 1), confirm=True)


def test_push_with_mocked_transport_writes_audit_log(monkeypatch, tmp_path):
    monkeypatch.setenv("ERP_PUSH_ENABLED", "1")
    for k, v in {"D365_TENANT_ID": "t", "D365_CLIENT_ID": "c", "D365_CLIENT_SECRET": "s", "D365_RESOURCE": "https://erp.example.invalid"}.items():
        monkeypatch.setenv(k, v)
    real = {"placeholder": False, "entities": {"schedule_lines": "RealEntity"},
            "fields": [{"source": "contract_ref", "target": "Ref", "type": "string", "required": True, "max_len": 64},
                       {"source": "amount", "target": "Amt", "type": "decimal", "required": True}]}
    monkeypatch.setattr(d365, "mapping", lambda: real)
    calls = []

    def handler(req: httpx.Request):
        calls.append((req.method, str(req.url)))
        if "login.microsoftonline.com" in str(req.url):
            return httpx.Response(200, json={"access_token": "tok"})
        assert req.headers["Authorization"] == "Bearer tok"
        return httpx.Response(201)

    class C(d365.D365Client):
        transport = httpx.MockTransport(handler)

    out = d365.push(make(), "cid", "n", None, date(2025, 1, 1), confirm=True, reviewer="QA", client_cls=C)
    assert out["pushed"] == 2 and out["rows"] == 2
    assert [m for m, u in calls if "/data/RealEntity" in u] == ["POST", "POST"]
    log = [json.loads(l) for l in (tmp_path / "audit" / "erp_push.jsonl").read_text().splitlines()]
    assert log[0]["contract_id"] == "cid" and log[0]["reviewer"] == "QA" and log[0]["result"] == "ok"
    assert "secret" not in json.dumps(log).lower() and "tok" not in json.dumps(log)


def test_push_missing_credentials_is_audited(monkeypatch, tmp_path):
    monkeypatch.setenv("ERP_PUSH_ENABLED", "1")
    monkeypatch.setattr(d365, "mapping", lambda: {"placeholder": False, "entities": {"schedule_lines": "E"},
                                                  "fields": [{"source": "amount", "target": "A", "type": "decimal", "required": True}]})
    with pytest.raises(d365.PushError, match="Missing environment variables"):
        d365.push(make(), "cid", "n", None, date(2025, 1, 1), confirm=True)
    assert json.loads((tmp_path / "audit" / "erp_push.jsonl").read_text().splitlines()[0])["result"] == "error"


def test_mapping_file_declares_placeholders():
    m = yaml.safe_load(open("erp/d365_mapping.yaml"))
    assert m["placeholder"] is True and all(f["target"].startswith("TODO_") for f in m["fields"])
