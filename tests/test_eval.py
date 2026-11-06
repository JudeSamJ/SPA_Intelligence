import json
from pathlib import Path

import pytest

from app import config
from app.extract import extract_contract
from eval.run_eval import aggregate, compare
from tests.fakes import FakeClient, oracle_input

SAMPLES = Path(__file__).resolve().parent.parent / "samples"
TRUTH = json.loads((SAMPLES.parent / "ground_truth.json").read_text())


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)


def score(name, mutate=None):
    p = SAMPLES / name
    inp = oracle_input(p)
    if mutate:
        mutate(inp)
    c = extract_contract(p.read_bytes(), name, client=FakeClient(inp))
    return compare(c, TRUTH[name], p.read_bytes())


def test_compare_perfect_extraction_scores_all_correct():
    for n in TRUTH:
        res = score(n)
        assert all(r["correct"] for r in res.values()), {k: v for k, v in res.items() if not v["correct"]}
        assert all(r["quote_ok"] in (True, None) for r in res.values())


def test_compare_detects_wrong_values_and_bad_quotes():
    def mut(i):
        i["price"]["value"] = 2450001.0
        i["buyer"]["value"] = "  LAYLA hassan   al mansoori "      # normalised match -> still correct
        i["handover_date"]["value"] = "2027-06-29"
        i["delay_cap"]["source_quote"] = "invented quote"
    res = score("sample_a.pdf", mut)
    assert not res["price"]["correct"] and not res["handover_date"]["correct"]
    assert res["buyer"]["correct"]
    assert res["delay_cap"]["quote_ok"] is False


def test_aggregate_math():
    per = {"x": {"f": {"correct": True, "quote_ok": True}}, "y": {"f": {"correct": False, "quote_ok": False}}}
    a = aggregate(per)
    assert a["fields"]["f"]["accuracy"] == 0.5 and a["overall"]["quote_accuracy"] == 0.5


def test_ground_truth_sample_c_is_95():
    assert sum(m["percent"] for m in TRUTH["sample_c.pdf"]["payment_plan"]) == 95
    assert TRUTH["sample_c.pdf"]["has_cancellation_clause"] is False
