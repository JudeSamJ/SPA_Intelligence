"""Designed emails and image cards: signing, rendering, HTML safety, webhook payload, public routes, test-send."""
import io
import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import emailcards as ec
from app import notifiers as nf
from backend.api.main import create_app

SECRET = "card-secret-" + "x" * 20
ST = {"base": "https://app.example.test", "secret": SECRET, "name": "Jude Sam J", "title": "Unlimited Innovations India Pvt. Ltd"}
CID = "a" * 64
CONTRACT = {"contract": {"contract_id": CID, "contract_name": "sample_a.pdf", "unit_id": "MCR-1204", "buyer": "Layla Hassan Al Mansoori",
                         "currency": "AED", "price": 2450000.0, "handover_date": "2027-06-30", "jurisdiction": "ae_dubai", "milestones": 5,
                         "payment_plan_percent_sum": 100.0, "warnings": 0, "needs_review": 2,
                         "plan": [{"name": f"M{i}", "percent": 20, "due_date": f"202{5 + i // 3}-0{1 + i}-15"} for i in range(5)]}}
ALERT = {"alert": {"contract_id": CID, "contract_name": "sample_a.pdf", "event_type": "overdue", "severity": "high", "message": "m",
                   "due_date": "2026-03-15", "days_until": -237, "label": "Second Instalment (20%)", "page": 6}}
REVIEW = {"review": {"contract_id": CID, "contract_name": "sample_a.pdf", "field": "price", "status": "partial", "confidence": 0.82, "page": 3}}


def png_size(b: bytes):
    im = Image.open(io.BytesIO(b))
    assert im.format == "PNG"
    return im.size


# ---- signing -------------------------------------------------------------------------------------------------------
def test_signed_payload_roundtrip_and_rejections():
    p = ec.card_payload("alert", ALERT)
    d, sig = ec.card_params(SECRET, p)
    assert ec.decode_card(d, sig, SECRET)["lab"] == "Second Instalment (20%)"
    with pytest.raises(ec.CardError):
        ec.decode_card(d, sig, "another-secret-" + "y" * 20)                       # wrong secret
    with pytest.raises(ec.CardError):
        ec.decode_card(d[:-2] + "AA", sig, SECRET)                                 # tampered payload
    with pytest.raises(ec.CardError):
        ec.decode_card(d, "0" * 32, SECRET)                                        # forged signature
    with pytest.raises(ec.CardError):
        ec.decode_card(d, sig, "")                                                 # cards disabled without a secret
    d2, sig2 = ec.card_params(SECRET, p, now=time.time() - 31 * 86400)             # older than 30 days
    with pytest.raises(ec.CardError, match="expired"):
        ec.decode_card(d2, sig2, SECRET)


def test_payloads_hold_headline_facts_never_quotes():
    for kind, data in (("contract_ready", CONTRACT), ("alert", ALERT), ("review_needed", REVIEW)):
        raw = json.dumps(ec.card_payload(kind, data)).lower()
        assert "quote" not in raw and len(raw) < 1500


# ---- rendering -----------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("kind,data,size", [("contract_ready", CONTRACT, (1200, 640)), ("alert", ALERT, (1200, 470)), ("review_needed", REVIEW, (1200, 480))])
def test_cards_render_to_png_of_the_designed_size(kind, data, size):
    assert png_size(ec.render_card(ec.card_payload(kind, data))) == size


def test_rendering_survives_missing_long_and_odd_values():
    weird = [{"k": "c"}, {"k": "a", "d": "soon", "sev": "nope"}, {"k": "r", "cf": "abc"},
             {"k": "c", "u": "U" * 500, "b": "<b>x</b>" * 50, "p": "NaN", "pl": [[1, 2], ["x", "y", "z"], [None, 500, "bad"]] * 6, "m": "many", "w": None},
             {"k": "a", "lab": "L" * 400, "d": 10 ** 9, "pg": "x" * 50}, {"k": "r", "f": "a.b.c", "cf": 7}]
    for p in weird:
        assert png_size(ec.render_card(p))[0] == 1200


def test_plan_percentages_over_100_do_not_overflow_the_bar():
    p = ec.card_payload("contract_ready", CONTRACT) | {"pl": [["a", 90, None], ["b", 90, None], ["c", 90, None]]}
    assert png_size(ec.render_card(p)) == (1200, 640)


# ---- the HTML email -------------------------------------------------------------------------------------------------
def test_email_has_hero_logo_signoff_disclaimer_and_deep_link():
    e = ec.build_email("contract_ready", CONTRACT, ST)
    h = e["html"]
    assert e["subject"] == "Contract ready · MCR-1204 · sample_a.pdf"
    assert "https://app.example.test/api/card.png?d=" in h and "&amp;sig=" in h and e["image_url"] in h.replace("&amp;", "&")
    assert 'src="https://app.example.test/api/brand/logo.png"' in h and "Unlimited Innovations India Pvt. Ltd" in h
    assert "With regards," in h and "Jude Sam J" in h and h.index("With regards,") < h.index("brand/logo.png")      # logo at the very bottom
    assert "Decision support, not legal advice." in h and f"/app/contracts/{CID}/terms" in h
    assert "AED 2,450,000" in h and "30 Jun 2027" in h and "Dubai (UAE)" in h                                      # facts also as text (images may be blocked)
    assert "<script" not in h.lower() and "width:100%;max-width:600px" in h and 'alt="' in h


def test_alert_and_review_emails():
    a = ec.build_email("alert", ALERT, ST)
    assert a["subject"].startswith("HIGH · Second Instalment (20%)") and "237 day(s) overdue" in a["html"]
    assert f"/app/contracts/{CID}/obligations" in a["html"] and "cannot see whether a payment was made" in a["html"]
    r = ec.build_email("review_needed", REVIEW, ST)
    assert r["subject"] == "Review needed · Price · sample_a.pdf" and "82%" in r["html"] and f"/app/contracts/{CID}/terms" in r["html"]


def test_hostile_text_is_escaped_everywhere():
    evil = "<script>alert(1)</script>\"><img src=x onerror=alert(2)>"
    c = json.loads(json.dumps(CONTRACT))
    c["contract"].update(contract_name=evil, buyer=evil, unit_id=evil)
    h = ec.build_email("contract_ready", c, {**ST, "name": evil, "title": evil})["html"]
    assert "<script>alert(1)" not in h and "onerror=alert(2)>" not in h and "&lt;script&gt;" in h


def test_bad_contract_id_gives_no_deep_link_and_missing_settings_degrade_gracefully():
    c = json.loads(json.dumps(CONTRACT)); c["contract"]["contract_id"] = "../../etc/passwd"
    assert "/app/contracts/" not in ec.build_email("contract_ready", c, ST)["html"]
    bare = ec.build_email("contract_ready", CONTRACT, {"base": "", "secret": "", "name": "X", "title": "T"})
    assert "<img" not in bare["html"] and "AED 2,450,000" in bare["html"] and "With regards," in bare["html"] and bare["image_url"] == ""


def test_local_preview_references_files_not_urls():
    h = ec.build_email("alert", ALERT, {**ST, "base": "", "secret": ""}, local_dir="")["html"]
    assert 'src="card_alert.png"' in h and 'src="logo.png"' in h


# ---- webhook payload -------------------------------------------------------------------------------------------------
def test_webhook_event_carries_the_finished_email(monkeypatch):
    for k, v in (("PUBLIC_BASE_URL", ST["base"]), ("ALERT_WEBHOOK_SECRET", SECRET), ("EMAIL_SENDER_NAME", "Jude Sam J")):
        monkeypatch.setenv(k, v)
    got = []
    h = nf.WebhookNotifier("https://flow.example.test/x", SECRET)
    h.transport = httpx.MockTransport(lambda r: (got.append(json.loads(r.content)), httpx.Response(202))[1])
    assert h.post("alert", ALERT)
    ev = got[0]
    assert ev["type"] == "alert" and ev["alert"]["label"] == "Second Instalment (20%)"                 # the plain event is still there
    assert ev["email"]["subject"].startswith("HIGH") and "With regards," in ev["email"]["html"] and ev["email"]["image_url"].startswith("https://app.example.test/api/card.png")
    assert "quote" not in json.dumps(ev).lower()


def test_design_failure_never_blocks_the_plain_event(monkeypatch):
    monkeypatch.setattr(ec, "build_email", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    got = []
    h = nf.WebhookNotifier("https://flow.example.test/x", "")
    h.transport = httpx.MockTransport(lambda r: (got.append(json.loads(r.content)), httpx.Response(202))[1])
    assert h.post("alert", ALERT) and "email" not in got[0]


# ---- public routes + test send ----------------------------------------------------------------------------------------
@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SPA_DISABLE_SCHEDULER", "1")
    monkeypatch.setenv("ALERT_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("PUBLIC_BASE_URL", ST["base"])
    return TestClient(create_app())


def test_card_and_logo_routes_are_public_and_strict(client, monkeypatch):
    monkeypatch.setenv("AUTH_MODE", "apikey")
    monkeypatch.setenv("API_KEYS", json.dumps({"k" * 30: {"name": "m", "roles": ["Spa.Staff"]}}))
    c = TestClient(create_app())                                          # auth ON: the email client has no credentials
    d, sig = ec.card_params(SECRET, ec.card_payload("alert", ALERT))
    ok = c.get("/api/card.png", params={"d": d, "sig": sig})
    assert ok.status_code == 200 and ok.headers["content-type"] == "image/png" and png_size(ok.content) == (1200, 470)
    assert c.get("/api/card.png", params={"d": d, "sig": "0" * 32}).status_code == 404
    assert c.get("/api/card.png", params={"d": d + "x", "sig": sig}).status_code == 404
    assert c.get("/api/card.png").status_code == 422
    logo = c.get("/api/brand/logo.png")
    assert logo.status_code == 200 and png_size(logo.content)[0] == 640
    assert c.get("/api/contracts").status_code == 401                      # everything else stays locked


def test_card_route_is_off_without_a_secret(monkeypatch):
    monkeypatch.setenv("SPA_DISABLE_SCHEDULER", "1")
    monkeypatch.delenv("ALERT_WEBHOOK_SECRET", raising=False)
    d, sig = ec.card_params(SECRET, ec.card_payload("alert", ALERT))
    assert TestClient(create_app()).get("/api/card.png", params={"d": d, "sig": sig}).status_code == 404


def test_webhook_test_endpoint(client, monkeypatch):
    monkeypatch.delenv("ALERT_WEBHOOK_URL", raising=False)
    assert client.post("/api/webhook/test", json={"kind": "alert"}).status_code == 409
    assert client.post("/api/webhook/test", json={"kind": "bogus"}).status_code == 422
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "https://flow.example.test/x")
    got = []
    monkeypatch.setattr(nf.WebhookNotifier, "transport", httpx.MockTransport(lambda r: (got.append(json.loads(r.content)), httpx.Response(202))[1]), raising=False)
    for kind in ("contract_ready", "alert", "review_needed"):
        r = client.post("/api/webhook/test", json={"kind": kind}).json()
        assert r["sent"] is True and r["kind"] == kind
    assert [g["type"] for g in got] == ["contract_ready", "alert", "review_needed"]
    assert all(g["test"] is True and g["email"]["subject"].startswith("[TEST] ") and "With regards," in g["email"]["html"] for g in got)


def test_fuzz_random_junk_never_breaks_a_card_or_an_email():
    import random
    r = random.Random(1234)
    junk = [None, "", "x" * 300, "<b>&\"", 0, -5, 10 ** 12, 3.7, float("nan"), float("inf"), True, [], [1, 2], {"a": 1}, "2026-13-45", "NaN", "2027-06-30"]
    keys = {"c": ["u", "b", "n", "cur", "p", "h", "j", "m", "s", "w", "r", "pl"], "a": ["n", "lab", "ev", "sev", "due", "d", "pg"],
            "r": ["n", "f", "st", "cf", "pg"]}
    kinds = {"c": "contract_ready", "a": "alert", "r": "review_needed"}
    for k, ks in keys.items():
        for _ in range(25):
            p = {"k": k, **{x: r.choice(junk) for x in ks if r.random() < 0.85}}
            if k == "c" and r.random() < 0.7:
                p["pl"] = [[r.choice(junk), r.choice(junk), r.choice(junk)] for _ in range(r.randint(0, 12))]
            assert png_size(ec.render_card(p))[0] == 1200
    # the same junk through the event -> email path
    for kind, key, fields in (("contract_ready", "contract", keys["c"]), ("alert", "alert", keys["a"]), ("review_needed", "review", keys["r"])):
        for _ in range(80):
            ev = {key: {f: r.choice(junk) for f in ("contract_id", "contract_name", "unit_id", "buyer", "currency", "price", "handover_date",
                                                     "jurisdiction", "milestones", "payment_plan_percent_sum", "warnings", "needs_review",
                                                     "label", "event_type", "severity", "due_date", "days_until", "page", "field", "status",
                                                     "confidence", "message", "plan") if r.random() < 0.8}}
            e = ec.build_email(kind, ev, ST)
            assert "<html" in e["html"] and e["subject"]


def test_font_fallback_still_renders_when_bundled_fonts_are_missing(monkeypatch, tmp_path):
    ec.font.cache_clear()
    monkeypatch.setattr(ec, "ASSETS", tmp_path)                      # no assets/fonts here
    try:
        assert png_size(ec.render_card(ec.card_payload("contract_ready", CONTRACT))) == (1200, 640)
    finally:
        ec.font.cache_clear()
