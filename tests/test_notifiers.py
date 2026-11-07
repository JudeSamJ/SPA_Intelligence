import json
import time

import httpx
import pytest

from app import notifiers as nf
from app import obligations as ob


def alert(**kw):
    return {"id": "a1", "contract_id": "c" * 64, "contract_name": "n", "event_type": "overdue", "severity": "high",
            "message": "Booking: overdue, due 2025-03-15", "due_date": "2025-03-15", "days_until": -1, "label": "Booking",
            "evidence": {"page": 6, "quote": "SECRET CONTRACT TEXT"}, **kw}


def hook(handler, secret="s3cret"):
    h = nf.WebhookNotifier("https://prod.example.invalid/hook", secret)
    h.transport = httpx.MockTransport(handler)
    return h


def test_payload_is_signed_and_has_no_contract_text():
    seen = {}

    def handler(req):
        seen.update(body=req.content, headers=dict(req.headers))
        return httpx.Response(202)

    hook(handler).notify(alert())
    body = json.loads(seen["body"])
    assert body["type"] == "alert" and body["alert"]["page"] == 6 and body["alert"]["severity"] == "high"
    assert b"SECRET CONTRACT TEXT" not in seen["body"]
    h = seen["headers"]
    assert nf.verify("s3cret", h["x-spa-timestamp"], seen["body"], h["x-spa-signature"])
    assert not nf.verify("wrong", h["x-spa-timestamp"], seen["body"], h["x-spa-signature"])
    assert not nf.verify("s3cret", h["x-spa-timestamp"], seen["body"] + b" ", h["x-spa-signature"])          # tampered
    assert not nf.verify("s3cret", h["x-spa-timestamp"], seen["body"], h["x-spa-signature"], now=time.time() + 1000)   # replay window


def test_failures_never_raise():
    assert hook(lambda r: httpx.Response(500)).post("alert", {}) is False

    def boom(req):
        raise httpx.ConnectError("down")
    nf.CompositeNotifier(hook(boom)).notify(alert())            # must not raise


def test_http_url_refused_except_localhost():
    with pytest.raises(ValueError):
        nf.WebhookNotifier("http://example.com/x")
    nf.WebhookNotifier("http://localhost:7071/x")


def test_build_notifier_is_opt_in(monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert isinstance(nf.build_notifier(), ob.LoggingNotifier)
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://prod.example.invalid/hook")
    assert isinstance(nf.build_notifier(), nf.CompositeNotifier)


def test_review_items_sent_once(monkeypatch, tmp_path):
    monkeypatch.setenv("SPA_NOTIFY_STATE", str(tmp_path / "state.json"))
    got = []
    h = hook(lambda r: (got.append(json.loads(r.content)), httpx.Response(200))[1])
    items = [{"contract_id": "c" * 64, "contract_name": "n", "field": "price", "status": "partial", "confidence": 0.8, "source_page": 3}]
    assert nf.notify_new_review_items(items, h) == 1
    assert nf.notify_new_review_items(items, h) == 0                      # same item: not sent again
    assert nf.notify_new_review_items(items + [{**items[0], "field": "buyer"}], h) == 1
    assert got[0]["type"] == "review_needed" and got[0]["review"]["field"] == "price"
    assert nf.notify_new_review_items(items, None) == 0                   # no webhook configured: nothing sent


def test_failed_delivery_is_retried_next_time(monkeypatch, tmp_path):
    monkeypatch.setenv("SPA_NOTIFY_STATE", str(tmp_path / "state.json"))
    items = [{"contract_id": "c" * 64, "field": "price"}]
    assert nf.notify_new_review_items(items, hook(lambda r: httpx.Response(500))) == 0
    assert nf.notify_new_review_items(items, hook(lambda r: httpx.Response(200))) == 1


def test_contract_ready_event_has_headline_facts_and_no_text(monkeypatch):
    from pathlib import Path
    from app.extract import extract_from_llm, pdf_pages, postprocess
    from app.schema import ContractData
    from tests.fakes import FakeClient, oracle_input
    p = Path("samples/sample_c.pdf")
    b = p.read_bytes()
    c = postprocess(ContractData(**extract_from_llm(b, FakeClient(oracle_input(p))).model_dump()), pdf_pages(b), b)
    got = []
    h = hook(lambda r: (got.append(r.content), httpx.Response(200))[1])
    assert nf.notify_contract_ready("c" * 64, "sample_c.pdf", c, h) is True
    j = json.loads(got[0])
    assert j["type"] == "contract_ready" and j["contract"]["price"] == 3980000.0 and j["contract"]["payment_plan_percent_sum"] == 95
    assert j["contract"]["warnings"] >= 1 and "quote" not in got[0].decode().lower()
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert nf.notify_contract_ready("c" * 64, "x", c) is False          # opt-in: nothing sent without a webhook
