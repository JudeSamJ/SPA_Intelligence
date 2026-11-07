"""Evidence, review queue, jurisdiction, statute-gap endpoints (LLM mocked)."""
import json

from app import config
from app.extract import extract_contract
from backend.tests.test_api import SAMPLES, FakeClient, client, env, oracle_input, seeded, sid  # noqa: F401  (fixtures)


def test_evidence_endpoint_returns_rects_and_page(client, seeded):
    cid = sid("sample_a.pdf")
    j = client.get(f"/api/contracts/{cid}/evidence/price").json()
    assert j["evidence"]["bbox"] and j["evidence"]["page"] >= 1 and j["grounding_status"] == "grounded"
    assert j["evidence"]["page_width"] > 0
    j2 = client.get(f"/api/contracts/{cid}/evidence/payment_plan.2").json()
    assert j2["evidence"]["rects"]
    assert client.get(f"/api/contracts/{cid}/evidence/nope").status_code == 404
    assert client.get(f"/api/contracts/{cid}/evidence/payment_plan.99").status_code == 404


def test_page_image_png(client, seeded):
    r = client.get(f"/api/contracts/{sid('sample_a.pdf')}/page/1.png")
    assert r.status_code == 200 and r.content[:4] == b"\x89PNG"
    assert client.get(f"/api/contracts/{sid('sample_a.pdf')}/page/99.png").status_code == 404


def test_jurisdiction_detection_and_override(client, seeded):
    a, d = sid("sample_a.pdf"), sid("sample_d_rera.pdf")
    assert client.get(f"/api/contracts/{a}").json()["contract"]["jurisdiction_detected"]["value"] == "ae_dubai"
    cd = client.get(f"/api/contracts/{d}").json()["contract"]
    assert cd["jurisdiction_detected"]["value"] == "in_rera" and cd["currency"] == "INR"
    assert client.put(f"/api/contracts/{d}/jurisdiction", json={"jurisdiction": "ae_dubai"}).json()["jurisdiction"] == "ae_dubai"
    assert client.put(f"/api/contracts/{d}/jurisdiction", json={"jurisdiction": "zz"}).status_code == 422
    assert client.put(f"/api/contracts/{d}/jurisdiction", json={"jurisdiction": None}).json()["jurisdiction"] == "in_rera"


def test_review_correct_overrides_and_flags_human_verified(client, seeded):
    cid = sid("sample_a.pdf")
    r = client.post(f"/api/contracts/{cid}/fields/price/review",
                    json={"action": "correct", "value": 2500000, "note": "typo in PDF", "reviewer": "QA"})
    assert r.status_code == 200
    c = client.get(f"/api/contracts/{cid}").json()["contract"]
    assert c["price"]["value"] == 2500000 and c["price"]["human_verified"] and c["price"]["review"]["reviewer"] == "QA"
    assert client.post(f"/api/contracts/{cid}/fields/price/review", json={"action": "correct", "value": "abc"}).status_code == 422
    assert client.post(f"/api/contracts/{cid}/fields/nope/review", json={"action": "accept"}).status_code == 422
    hist = client.get(f"/api/contracts/{cid}/reviews").json()["decisions"]
    assert hist[0]["at"] and hist[0]["note"] == "typo in PDF"


def test_review_queue_lists_and_clears(client, env):
    # a contract whose quote is only a fuzzy match -> partial -> needs review
    p = SAMPLES / "sample_a.pdf"
    inp = oracle_input(p)
    inp["delay_cap"]["source_quote"] = inp["delay_cap"]["source_quote"].replace("shall not exceed", "shall never exceed")
    extract_contract(p.read_bytes(), p.name, client=FakeClient(inp))
    q = client.get("/api/review-queue").json()
    assert q["count"] == 1 and q["items"][0]["field"] == "delay_cap" and q["items"][0]["status"] == "partial"
    cid = sid("sample_a.pdf")
    client.post(f"/api/contracts/{cid}/fields/delay_cap/review", json={"action": "accept", "reviewer": "QA"})
    assert client.get("/api/review-queue").json()["count"] == 0


def test_golden_export_requires_review_then_writes(client, env, monkeypatch, tmp_path):
    p = SAMPLES / "sample_a.pdf"
    inp = oracle_input(p)
    inp["price"]["source_quote"] = "AED 1 on the moon"
    extract_contract(p.read_bytes(), p.name, client=FakeClient(inp))
    cid = sid("sample_a.pdf")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    assert client.post(f"/api/contracts/{cid}/golden-export").status_code == 409
    client.post(f"/api/contracts/{cid}/fields/price/review",
                json={"action": "correct", "value": 2450000, "source_page": 1, "source_quote": "AED 2,450,000"})
    r = client.post(f"/api/contracts/{cid}/golden-export")
    assert r.status_code == 200, r.text
    labels = json.loads((tmp_path / r.json()["path"] / "labels.json").read_text())
    assert labels["price"]["value"] == 2450000 and labels["price"]["human_verified"] and labels["synthetic"] is False


def test_ungrounded_row_can_be_accepted_back(client, env):
    p = SAMPLES / "sample_a.pdf"
    inp = oracle_input(p)
    inp["payment_plan"][0]["source_quote"] = "Booking made-up row"
    extract_contract(p.read_bytes(), p.name, client=FakeClient(inp))
    cid = sid("sample_a.pdf")
    assert len(client.get(f"/api/contracts/{cid}").json()["contract"]["payment_plan"]) == 4
    client.post(f"/api/contracts/{cid}/fields/ungrounded_rows.1/review", json={"action": "accept"})
    assert len(client.get(f"/api/contracts/{cid}").json()["contract"]["payment_plan"]) == 5


def test_statute_gap_api_india_and_dubai(client, seeded):
    d = sid("sample_d_rera.pdf")
    r = client.post(f"/api/contracts/{d}/statute-gap", json={"delay_days": 180, "as_of_date": "2027-01-01"}).json()
    assert r["can_compute"] and r["jurisdiction"] == "in_rera" and r["currency"] == "INR"
    assert r["statutory"]["rate_table"]["illustrative"] is True and r["unreviewed"] is True
    assert r["shortfall"] > 0 and r["one_sided"] and r["evidence"]["delay_rate"]["page"]
    assert r["amounts_paid_source"] == "payment_plan"
    custom = client.post(f"/api/contracts/{d}/statute-gap", json={
        "delay_days": 30, "as_of_date": "2027-01-01",
        "amounts_paid": [{"date": "2026-01-01", "amount": 1000000}]}).json()
    assert custom["amounts_paid_source"] == "user" and custom["statutory"]["amount"] > 0
    a = client.post(f"/api/contracts/{sid('sample_a.pdf')}/statute-gap", json={"delay_days": 90}).json()
    assert a["can_compute"] is False and a["needs_legal_review"] is True
    assert client.post(f"/api/contracts/{d}/statute-gap", json={"delay_days": -5}).status_code == 422


def test_packs_endpoint_marks_unreviewed(client):
    j = client.get("/api/packs").json()
    ids = {p["id"] for p in j["packs"]}
    assert ids == {"ae_dubai", "in_rera"}
    assert all(e["unreviewed"] and e["reviewed_by_lawyer"] is False for p in j["packs"] for e in p["entries"])


def test_eval_runs_engines_bakeoff_endpoints(client, seeded, monkeypatch, tmp_path):
    import eval.run_eval as ev
    monkeypatch.setattr(ev, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(ev, "penalty_test_pass_rate", lambda: {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0})
    assert client.get("/api/eval/runs").json()["runs"] == []
    run = ev.run_eval(use_cache=True, log=lambda *_: None)
    rs = client.get("/api/eval/runs").json()["runs"]
    assert rs[0]["run_id"] == run["run_id"] and rs[0]["overall"]["f1"] == 1.0
    assert client.get(f"/api/eval/runs/{run['run_id']}").json()["fields"]["price"]["f1"] == 1.0
    assert client.get("/api/eval/runs/nope").status_code == 404
    es = {e["name"]: e for e in client.get("/api/eval/engines").json()["engines"]}
    assert es["claude_pdf"]["configured"] and not es["docling"]["configured"]
    b = client.get("/api/eval/bakeoff").json()
    assert b["golden_size"] == 4 and b["golden_real"] == 0 and "only to our golden set" in b["note"]
    row = {e["name"]: e for e in b["engines"]}
    assert row["claude_pdf"]["run"]["fields"]["price"] == 1.0 and row["docling"]["run"] is None


def test_montecarlo_endpoints(client, seeded):
    d = sid("sample_d_rera.pdf")
    body = {"as_of_date": "2027-01-01", "trials": 1000, "seed": 3}
    a = client.post(f"/api/contracts/{d}/montecarlo", json=body).json()
    b = client.post(f"/api/contracts/{d}/montecarlo", json=body).json()
    assert a == b and a["assumption_driven"] is True and a["statutory"]["p90"] >= a["statutory"]["p50"]
    fixed = client.post(f"/api/contracts/{d}/montecarlo", json={**body, "family": "fixed", "params": {"days": 180}}).json()
    det = client.post(f"/api/contracts/{d}/statute-gap", json={"delay_days": 180, "as_of_date": "2027-01-01"}).json()
    assert fixed["statutory"]["p50"] == det["statutory"]["amount"]
    assert client.post(f"/api/contracts/{d}/montecarlo", json={**body, "params": {"zzz": 1}, "family": "fixed"}).status_code == 422
    assert client.post(f"/api/contracts/{d}/montecarlo", json={**body, "signal_csv": "bad"}).status_code == 422
    sig = client.post(f"/api/contracts/{d}/montecarlo", json={**body, "signal_csv": "date,planned_progress_pct,actual_progress_pct\n2026-06-01,60,50"}).json()
    assert sig["assumptions"]["signal"]["shift_days"] == 40 and sig["delay_days"]["p50"] > a["delay_days"]["p50"]
    p = client.post("/api/portfolio/montecarlo", json=body).json()
    assert set(p["totals_by_currency"]) == {"AED", "INR"} and len(p["rows"]) == 4


def test_obligations_and_alerts_api(client, seeded):
    r = client.get("/api/obligations", params={"as_of": "2025-03-10", "within_days": 30}).json()
    assert r["as_of"] == "2025-03-10" and r["obligations"]
    assert all(o["evidence"]["quote"] and o["days_until"] <= 30 for o in r["obligations"])
    assert {o["status"] for o in r["obligations"]} <= {"due_soon", "overdue", "upcoming", "past"} | set(r["event_types"])
    rc = client.post("/api/alerts/recompute", params={"as_of": "2025-03-16"}).json()
    assert rc["alerts"] > 0
    al = client.get("/api/alerts").json()
    assert al["delivery"] == "in-app feed only" and al["unacked"] == len(al["alerts"]) > 0
    first = al["alerts"][0]
    assert client.post(f"/api/alerts/{first['id']}/ack").json()["acked"] is True
    assert client.get("/api/alerts").json()["unacked"] == al["unacked"] - 1
    assert client.post("/api/alerts/zzz/ack").status_code == 404
    one = client.get("/api/obligations", params={"as_of": "2025-03-10", "contract_id": sid("sample_a.pdf")}).json()
    assert {o["contract_id"] for o in one["obligations"]} == {sid("sample_a.pdf")}
