"""Golden-set eval, run history/regressions, engines (LLM mocked, no network)."""
import json
from pathlib import Path

import httpx
import pytest

from app import config
from app.engines import cost_usd, get_engine, list_engines
from app.extract import extract_contract
from eval import run_eval as ev
from tests.fakes import FakeClient, oracle_input

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(config, "EVAL_RESULTS_PATH", tmp_path / "results.json")
    monkeypatch.setattr(ev, "RUNS_DIR", tmp_path / "runs")
    monkeypatch.setattr(ev, "penalty_test_pass_rate", lambda: {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0})
    monkeypatch.setattr(config, "PROVIDER", "azure_openai")
    for k in ("AZURE_OPENAI_API_KEY", "AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_DEPLOYMENT"):
        monkeypatch.setenv(k, "x")
    return tmp_path


def seed(mutate=None):
    for p in sorted(SAMPLES.glob("sample_*.pdf")):
        inp = oracle_input(p)
        if mutate:
            mutate(p.name, inp)
        extract_contract(p.read_bytes(), p.name, client=FakeClient(inp), use_cache=False)


def test_golden_set_loads_and_is_labelled_synthetic():
    g = ev.load_golden()
    assert len(g) == 4 and all(d["synthetic"] for d in g)
    assert all(d["labels"]["price"]["page"] for d in g)


def test_perfect_run_scores_one_and_no_hallucinations(env):
    seed()
    # golden docs hash identically to samples, so the seeded cache is used
    run = ev.run_eval(use_cache=True, allow_llm=False, log=lambda *_: None)
    assert run["overall"]["f1"] == 1.0 and run["overall"]["hallucinations"] == 0
    assert run["overall"]["grounding_pass_rate"] == 1.0
    assert run["golden"] == {"size": 4, "synthetic": 4, "real": 0, "docs": run["golden"]["docs"]}
    assert run["table"]["row_f1"] == 1.0 and run["table"]["sum_correct"] == 4
    assert (env / "runs" / f"{run['run_id']}.json").exists() and run["compared_to"] is None
    assert run["git_commit"]


def test_wrong_and_ungrounded_values_hit_precision_recall_hallucinations(env):
    def mut(name, inp):
        if name == "sample_a.pdf":
            inp["price"]["value"] = 999.0                                 # wrong value, real quote -> ungrounded (value not in quote)
            inp["handover_date"]["value"] = "2027-06-29"                 # wrong date -> ungrounded
        if name == "sample_b.pdf":
            inp["buyer"]["source_quote"] = "someone who is not in the file"
    seed(mut)
    run = ev.run_eval(use_cache=True, log=lambda *_: None)
    f = run["fields"]
    assert f["price"]["recall"] == 0.75 and f["price"]["precision"] == 1.0     # abstained on 1 of 4 -> FN, no FP
    assert f["buyer"]["recall"] == 0.75
    assert run["overall"]["hallucinations"] == 3
    assert run["overall"]["abstention_rate"] > 0
    assert run["overall"]["f1"] < 1.0


def test_second_run_flags_regressions_vs_previous(env):
    seed()
    first = ev.run_eval(use_cache=True, log=lambda *_: None)
    assert first["regressions"] == []
    seed(lambda n, i: i["unit_id"].update(value="WRONG") if n == "sample_c.pdf" else None)
    import time; time.sleep(1.1)       # run ids are second-resolution timestamps
    second = ev.run_eval(use_cache=True, log=lambda *_: None)
    assert second["compared_to"] == first["run_id"]
    assert any(r["metric"] == "unit_id.f1" for r in second["regressions"])
    assert any(r["metric"] == "hallucinations" for r in second["regressions"])
    assert len(ev.list_runs()) == 2


def test_eval_refuses_llm_without_permission(env):
    with pytest.raises(ev.EvalNeedsLLM):
        ev.run_eval(use_cache=True, allow_llm=False, log=lambda *_: None)


def test_cli_model_flag_sets_model(env, monkeypatch, capsys):
    seed()
    monkeypatch.setattr(config, "MODEL", "old")
    # a model swap invalidates the cache (cache key includes the model), so the CLI asks for --yes before any LLM call
    assert ev.main(["--model", "gpt-test"]) == 3
    assert config.MODEL == "gpt-test"
    assert "gpt-test" in capsys.readouterr().err


def test_engines_report_not_configured_never_faked(monkeypatch):
    for k in ("AZURE_DOCINT_ENDPOINT", "AZURE_DOCINT_KEY"):
        monkeypatch.delenv(k, raising=False)
    es = {e["name"]: e for e in list_engines()}
    assert es["azure_docint"]["configured"] is False and "AZURE_DOCINT_ENDPOINT" in es["azure_docint"]["reason"]
    assert es["docling"]["configured"] is False and "pip install docling" in es["docling"]["reason"]
    with pytest.raises(Exception, match="not configured"):
        get_engine("azure_docint").extract(SAMPLES / "sample_a.pdf")


def test_cost_is_none_until_prices_set_and_computed_from_usage(monkeypatch):
    assert cost_usd(1000, 500, 5) is None
    import app.engines as eng
    monkeypatch.setattr(eng, "pricing", lambda: {"llm": {"input_per_million_tokens": 2.0, "output_per_million_tokens": 8.0},
                                                 "docint": {"layout_per_1000_pages": 10.0}})
    # 1,000,000 in x $2 + 500,000 out x $8 /1e6 = 2 + 4 = 6.0 ; docint 100 pages = 100/1000 x 10 = 1.0
    assert cost_usd(1_000_000, 500_000, 5) == 6.0
    assert cost_usd(1_000_000, 500_000, 5, docint_pages=100) == 7.0


def test_azure_docint_engine_with_mock_transport(env, monkeypatch):
    from app.engines.azure_docint import AzureDocIntEngine
    monkeypatch.setenv("AZURE_DOCINT_ENDPOINT", "https://di.example.invalid")
    monkeypatch.setenv("AZURE_DOCINT_KEY", "k")
    pdf = SAMPLES / "sample_a.pdf"

    def handler(req: httpx.Request):
        if req.method == "POST":
            assert req.headers["Ocp-Apim-Subscription-Key"] == "k"
            return httpx.Response(202, headers={"operation-location": "https://di.example.invalid/op/1"})
        return httpx.Response(200, json={"status": "succeeded", "analyzeResult": {"pages": [{"lines": [{"content": "hello"}]}] * 6}})

    class Eng(AzureDocIntEngine):
        transport = httpx.MockTransport(handler)

    import app.engines as engines_mod
    monkeypatch.setattr(engines_mod, "extract_from_llm", lambda pdf_bytes, client=None, pages=None: __import__("app.extract", fromlist=["x"]).extract_from_llm(pdf_bytes, FakeClient(oracle_input(pdf)), pages=pages))
    res = Eng().extract(pdf)
    assert res.metrics["docint_pages"] == 6 and res.contract.price.grounding.status == "grounded"
    assert res.metrics["engine"] == "azure_docint"
