"""API tests. The LLM is always mocked (fake clients from tests/fakes.py); no network, no keys."""
import io
import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app import config, llm
from app.extract import extract_contract, file_hash
from app.llm import AnthropicAdapter
from app.schema import ContractData, Sourced
from backend.api import deps
from backend.api.main import create_app
from tests.fakes import FakeClient, oracle_input

ROOT = Path(__file__).resolve().parents[2]
SAMPLES = ROOT / "samples"


def sid(name):
    return file_hash((SAMPLES / name).read_bytes())


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(config, "EVAL_RESULTS_PATH", tmp_path / "results.json")
    monkeypatch.setattr(config, "PROVIDER", "azure_openai")
    for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.setenv(k, "x")
    deps.JOBS.clear()
    for lim in (deps.upload_limiter, deps.chat_limiter):
        lim.hits.clear()
    return tmp_path


@pytest.fixture
def client(env):
    return TestClient(create_app())


@pytest.fixture
def seeded(env):
    for p in sorted(SAMPLES.glob("sample_*.pdf")):
        extract_contract(p.read_bytes(), p.name, client=FakeClient(oracle_input(p)))


def blank_pdf(text: str | None) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text)
    return doc.tobytes()


def wait_status(client, cid, want="extracted", timeout=5):
    t0 = time.time()
    while time.time() - t0 < timeout:
        s = client.get(f"/api/contracts/{cid}/status").json()["status"]
        if s == want or s == "error":
            return s
        time.sleep(0.05)
    return s


# ---------------------------------------------------------------- meta / errors
def test_health(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and j["llm_configured"] is True and j["llm_call_cap"] == config.MAX_LLM_CALLS


def test_error_shape_and_id_sanitising(client):
    r = client.get("/api/contracts/not-a-hash")
    assert r.status_code == 404 and set(r.json()) == {"error"} and r.json()["error"]["code"] == "not_found"
    assert client.get("/api/contracts/..%2F..%2Fetc%2Fpasswd/pdf").status_code == 404
    r = client.get(f"/api/contracts/{'0' * 64}")
    assert r.status_code == 404
    r = client.post(f"/api/contracts/{sid('sample_a.pdf')}/chat", json={"message": ""})
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"


def test_cors_allows_only_configured_origin(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:5173",
                                                 "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/health", headers={"Origin": "https://evil.example",
                                                  "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
    assert "*" not in config.CORS_ORIGINS


# ---------------------------------------------------------------- contracts
def test_list_contracts_shows_samples_not_extracted(client):
    rows = client.get("/api/contracts").json()
    assert {r["name"] for r in rows} >= {"sample_a.pdf", "sample_b.pdf", "sample_c.pdf"}
    assert all(r["status"] == "not_extracted" and len(r["id"]) == 64 for r in rows if r["source"] == "sample")


def test_detail_requires_extraction_then_returns_plan(client, seeded):
    cid = sid("sample_a.pdf")
    j = client.get(f"/api/contracts/{cid}").json()
    assert j["contract"]["price"]["value"] == 2450000 and j["pdf_url"].endswith("/pdf")
    assert len(j["plan"]) == 5 and j["plan"][0]["amount"] == 490000.0 and j["plan"][4]["type"] == "handover_linked"
    assert j["plan"][0]["source_quote"]
    rows = {r["name"]: r for r in client.get("/api/contracts").json()}
    assert rows["sample_a.pdf"]["status"] == "extracted" and rows["sample_a.pdf"]["buyer"]


def test_detail_409_when_not_extracted(client):
    r = client.get(f"/api/contracts/{sid('sample_a.pdf')}")
    assert r.status_code == 409 and r.json()["error"]["code"] == "not_extracted"


def test_pdf_endpoint(client):
    r = client.get(f"/api/contracts/{sid('sample_a.pdf')}/pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf" and r.content.startswith(b"%PDF-")


def test_extract_job_flow_with_mock_llm(client, env, monkeypatch):
    p = SAMPLES / "sample_c.pdf"
    monkeypatch.setattr("app.extract.get_llm", lambda c=None: AnthropicAdapter(FakeClient(oracle_input(p))))
    cid = sid("sample_c.pdf")
    r = client.post(f"/api/contracts/{cid}/extract")
    assert r.status_code == 202 and r.json()["status"] in ("queued", "running", "extracted")
    assert wait_status(client, cid) == "extracted"
    c = client.get(f"/api/contracts/{cid}").json()["contract"]
    assert c["payment_plan_percent_sum"] == 95
    assert any("sum to 95%" in w for w in c["warnings"]) and any("No cancellation clause" in w for w in c["warnings"])
    # already cached: no new LLM call, immediate 'extracted'
    monkeypatch.setattr("app.extract.get_llm", lambda c=None: pytest.fail("should not call the LLM"))
    assert client.post(f"/api/contracts/{cid}/extract").json()["status"] == "extracted"


def test_extract_error_is_reported_not_leaked(client, env, monkeypatch):
    def boom(c=None):
        raise llm.LLMError("deployment missing")
    monkeypatch.setattr("app.extract.get_llm", boom)
    cid = sid("sample_a.pdf")
    client.post(f"/api/contracts/{cid}/extract")
    assert wait_status(client, cid, "error") == "error"
    st = client.get(f"/api/contracts/{cid}/status").json()
    assert st["status"] == "error"


def test_extract_503_when_llm_not_configured(client, monkeypatch):
    monkeypatch.delenv("AZURE_OPENAI_API_KEY")
    r = client.post(f"/api/contracts/{sid('sample_a.pdf')}/extract")
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_not_configured"


# ---------------------------------------------------------------- upload
def upload(client, data: bytes, name="x.pdf", extract=False):
    return client.post(f"/api/contracts/upload?extract={'true' if extract else 'false'}",
                       files={"file": (name, io.BytesIO(data), "application/pdf")})


def test_upload_rejects_non_pdf_and_fake_pdf(client):
    assert upload(client, b"MZ\x90\x00 not a pdf", "evil.pdf").status_code == 415
    assert upload(client, b"just text", "a.txt").json()["error"]["code"] == "not_a_pdf"
    r = upload(client, b"%PDF-1.4 garbage garbage")
    assert r.status_code == 415 and r.json()["error"]["code"] == "not_a_pdf"


def test_upload_rejects_too_large(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 1000)
    r = upload(client, b"%PDF-" + b"0" * 5000)
    assert r.status_code == 413 and r.json()["error"]["code"] == "file_too_large"


def test_upload_accepts_pdf_and_sanitises_name(client, env):
    data = blank_pdf("Hello contract " * 20)
    r = upload(client, data, "../../etc/my<script>.pdf")
    assert r.status_code == 202 and r.json()["id"] == file_hash(data)
    names = [c["name"] for c in client.get("/api/contracts").json() if c["source"] == "upload"]
    assert names and "/" not in names[0] and "<" not in names[0]
    assert (env / "uploads" / f"{file_hash(data)}.pdf").exists()


def test_upload_scanned_pdf_cannot_be_extracted(client, env):
    data = blank_pdf(None)
    r = upload(client, data, extract=True)
    assert r.status_code == 422 and r.json()["error"]["code"] == "scanned_pdf"
    row = [c for c in client.get("/api/contracts").json() if c["id"] == file_hash(data)][0]
    assert row["scanned_suspect"] is True


def test_upload_rate_limited(client, monkeypatch):
    monkeypatch.setattr(deps.upload_limiter, "limit", 2)
    codes = [upload(client, b"nope").status_code for _ in range(3)]
    assert codes[:2] == [415, 415] and codes[2] == 429


# ---------------------------------------------------------------- penalty
def synthetic_contract(env, **over):
    data = blank_pdf("Synthetic contract page")
    base = dict(
        buyer=Sourced[str](value="B", source_page=1, source_quote="Synthetic"),
        unit_id=Sourced[str](value="U-1", source_page=1, source_quote="Synthetic"),
        price=Sourced[float](value=1_000_000.0, source_page=1, source_quote="Synthetic"),
        area_sqft=Sourced[float](value=1000.0, source_page=1, source_quote="Synthetic"),
        handover_date=Sourced[date](value=date(2027, 1, 1), source_page=1, source_quote="Synthetic"),
        grace_period_days=Sourced[int](value=30, source_page=1, source_quote="Synthetic"),
        delay_rate=Sourced[float](value=6.0, source_page=1, source_quote="Synthetic"),
        delay_basis=Sourced[str](value="percent_per_annum", source_page=1, source_quote="Synthetic"),
        delay_cap=Sourced[float](), payment_plan=[], cancellation_clause=Sourced[str](),
        model=config.model_tag(), file_hash=file_hash(data))
    base.update(over)
    c = ContractData(**base)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    (config.UPLOAD_DIR / f"{c.file_hash}.pdf").write_bytes(data)
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (config.CACHE_DIR / f"{c.file_hash}.json").write_text(c.model_dump_json())
    return c.file_hash


def test_penalty_headline_value_9863_01(client, env):
    cid = synthetic_contract(env)
    r = client.post(f"/api/contracts/{cid}/penalty", json={"scenarios": [90]})
    assert r.status_code == 200
    row = r.json()["rows"][0]
    assert row["penalty"] == 9863.01 and row["chargeable_days"] == 60 and row["grace_days"] == 30
    assert r.json()["terms"]["rate"]["value"] == 6.0


def test_penalty_default_scenarios_from_rules_and_validation(client, seeded):
    cid = sid("sample_a.pdf")
    j = client.post(f"/api/contracts/{cid}/penalty", json={}).json()
    assert [r["delay_days"] for r in j["rows"]] == config.load_rules()["penalty"]["scenarios_days"]
    assert j["rows"][0]["penalty"] == 0.0            # 30 days < 60-day grace
    assert client.post(f"/api/contracts/{cid}/penalty", json={"scenarios": [-1]}).status_code == 422
    assert client.post(f"/api/contracts/{cid}/penalty", json={"scenarios": [99999]}).status_code == 422


def test_penalty_fixed_basis_and_cap(client, seeded):
    j = client.post(f"/api/contracts/{sid('sample_b.pdf')}/penalty", json={"scenarios": [180]}).json()
    assert j["rows"][0]["penalty"] == 1770.04 and j["rows"][0]["cap_amount"] is None
    j = client.post(f"/api/contracts/{sid('sample_a.pdf')}/penalty", json={"scenarios": [365]}).json()
    assert j["rows"][0]["penalty"] == 122835.62 and j["rows"][0]["cap_reached"] is False


def test_penalty_unavailable_for_other_basis(client, env):
    cid = synthetic_contract(env, delay_basis=Sourced[str](value="other", source_page=1, source_quote="Synthetic"))
    r = client.post(f"/api/contracts/{cid}/penalty", json={"scenarios": [90]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "simulation_unavailable"


# ---------------------------------------------------------------- cashflow
def test_cashflow_sample_a(client, seeded):
    j = client.post(f"/api/contracts/{sid('sample_a.pdf')}/cashflow",
                    json={"granularity": "quarter", "delay_days": 180}).json()
    assert j["price"] == 2450000 and j["at_risk"]["linked_amount"] == 980000.0
    assert j["at_risk"]["penalty_exposure"] == 48328.77 and j["at_risk"]["at_risk_total"] == 1028328.77
    assert sum(p["amount_due"] for p in j["periods"]) == 2450000.0 and j["periods"][-1]["cumulative_pct"] == 100.0
    assert "construction" in j["at_risk_definition"] and j["max_delay_days"] >= 365
    m = client.post(f"/api/contracts/{sid('sample_a.pdf')}/cashflow", json={"granularity": "month"}).json()
    assert len(m["periods"]) > len(j["periods"])


def test_cashflow_sample_c_flags_plan_not_100(client, seeded):
    j = client.post(f"/api/contracts/{sid('sample_c.pdf')}/cashflow", json={}).json()
    assert j["at_risk"]["plan_total"] == round(0.95 * 3980000, 2)


# ---------------------------------------------------------------- chat
class Script:
    """Deterministic scripted 'model' (anthropic-style client): calls one tool then answers from its result."""

    def __init__(self, tool, name_for_text):
        self.step, self.tool, self.text = 0, tool, name_for_text
        self.messages = SimpleNamespace(create=self.create)

    def create(self, **kw):
        self.step += 1
        if self.step == 1:
            b = SimpleNamespace(type="tool_use", name=self.tool, id="t1", input={})
            return SimpleNamespace(content=[b])
        res = json.loads(kw["messages"][-1]["content"][0]["content"])
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=f"{self.text} {res['value']} (page {res['source_page']})")])


def test_chat_refuses_legal_advice_without_llm(client, seeded, monkeypatch):
    monkeypatch.setattr("app.agent.get_llm", lambda c=None: pytest.fail("LLM must not be called"))
    r = client.post(f"/api/contracts/{sid('sample_a.pdf')}/chat", json={"message": "can I cancel and get a refund?"})
    j = r.json()
    assert r.status_code == 200 and j["refused"] is True and "legal team" in j["answer"] and j["citations"] == []


def test_chat_answers_handover_with_citation(client, seeded, monkeypatch):
    monkeypatch.setattr("app.agent.get_llm", lambda c=None: AnthropicAdapter(Script("handover_date", "Handover is")))
    j = client.post(f"/api/contracts/{sid('sample_a.pdf')}/chat",
                    json={"message": "When is handover?", "history": []}).json()
    assert j["refused"] is False and "2027-06-30" in j["answer"] and j["tool_calls"] == ["handover_date"]
    assert j["citations"][0]["page"] == 3 and "30 June 2027" in j["citations"][0]["quote"]


def test_chat_rate_limited_and_validated(client, seeded, monkeypatch):
    monkeypatch.setattr(deps.chat_limiter, "limit", 1)
    cid = sid("sample_a.pdf")
    assert client.post(f"/api/contracts/{cid}/chat", json={"message": "can I cancel?"}).status_code == 200
    assert client.post(f"/api/contracts/{cid}/chat", json={"message": "can I cancel?"}).status_code == 429
    deps.chat_limiter.hits.clear()
    bad = client.post(f"/api/contracts/{cid}/chat", json={"message": "x" * 3000})
    assert bad.status_code == 422


def test_chat_409_when_not_extracted(client):
    r = client.post(f"/api/contracts/{sid('sample_a.pdf')}/chat", json={"message": "hi"})
    assert r.status_code == 409


def test_chat_llm_unavailable_maps_to_503(client, seeded, monkeypatch):
    def boom(c=None):
        raise llm.LLMError("Azure returned 404")
    monkeypatch.setattr("app.agent.get_llm", boom)
    r = client.post(f"/api/contracts/{sid('sample_a.pdf')}/chat", json={"message": "When is handover?"})
    assert r.status_code == 503 and r.json()["error"]["code"] == "llm_unavailable"


# ---------------------------------------------------------------- eval
def test_eval_results_404_then_ok(client, env):
    assert client.get("/api/eval/results").status_code == 404
    res = {"generated_at": "t", "model": "m", "files": ["a"], "overall": {"value_accuracy": 1.0, "checks": 1,
           "quote_accuracy": 1.0, "quotes_checked": 1},
           "fields": {"buyer": {"correct": 1, "total": 1, "accuracy": 1.0, "quote_valid": 1, "quote_total": 1,
                                "quote_accuracy": 1.0}},
           "penalty_tests": {"passed": 14, "failed": 0, "total": 14, "pass_rate": 1.0}, "per_file": {"a": {"buyer": True}}}
    config.EVAL_RESULTS_PATH.write_text(json.dumps(res))
    assert client.get("/api/eval/results").json()["overall"]["checks"] == 1


def test_eval_run_needs_confirmation_when_uncached(client, env):
    r = client.post("/api/eval/run", json={})
    assert r.status_code == 409 and r.json()["error"]["code"] == "llm_confirmation_required"


def test_eval_run_cached_completes(client, seeded, monkeypatch):
    import eval.run_eval as ev
    monkeypatch.setattr(ev, "penalty_test_pass_rate", lambda: {"passed": 14, "failed": 0, "total": 14, "pass_rate": 1.0})
    assert client.post("/api/eval/run", json={}).status_code == 202
    t0 = time.time()
    while client.get("/api/eval/run/status").json()["state"] == "running" and time.time() - t0 < 10:
        time.sleep(0.05)
    assert client.get("/api/eval/run/status").json()["state"] == "done"
    j = client.get("/api/eval/results").json()
    assert j["overall"]["value_accuracy"] == 1.0 and j["penalty_tests"]["total"] == 14


def test_responses_are_gzip_compressed_when_large(client):
    r = client.get("/openapi.json", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200 and r.headers.get("content-encoding") == "gzip"
