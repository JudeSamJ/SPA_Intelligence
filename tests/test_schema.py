from pathlib import Path

import pytest
from pydantic import ValidationError

from app import config
from app.extract import ExtractionError, extract_contract, locate_quote, normalize_text
from app.schema import ContractData, Milestone, Sourced
from tests.fakes import FakeClient, oracle_input

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


@pytest.fixture(autouse=True)
def tmp_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CACHE_DIR", tmp_path)


def run(name, client):
    p = SAMPLES / name
    return extract_contract(p.read_bytes(), source_name=name, client=client)


def test_sourced_requires_quote_when_value_present():
    with pytest.raises(ValidationError):
        Sourced[str](value="x")
    with pytest.raises(ValidationError):
        Sourced[str](value="x", source_page=1, source_quote="  ")
    assert Sourced[str]().value is None  # null is fine
    assert Sourced[float](value=None, source_page=2, source_quote="no cap").value is None


def test_milestone_percent_bounds():
    with pytest.raises(ValidationError):
        Milestone(name="x", percent=120, source_page=1, source_quote="q")


def test_sample_a_clean():
    d = run("sample_a.pdf", FakeClient(oracle_input(SAMPLES / "sample_a.pdf")))
    assert d.payment_plan_percent_sum == 100
    assert d.warnings == []
    assert d.price.value == 2450000 and d.price.source_page >= 1


def test_sample_b_no_cap_keeps_quote_and_null_value():
    d = run("sample_b.pdf", FakeClient(oracle_input(SAMPLES / "sample_b.pdf")))
    assert d.delay_cap.value is None and d.delay_cap.source_quote
    assert d.payment_plan_percent_sum == 100
    assert d.delay_basis.value == "fixed_per_sqft_per_year"


def test_sample_c_sum_and_missing_cancellation_warnings():
    d = run("sample_c.pdf", FakeClient(oracle_input(SAMPLES / "sample_c.pdf")))
    assert d.payment_plan_percent_sum == 95
    assert any("sum to 95%" in w for w in d.warnings)
    assert any("No cancellation clause" in w for w in d.warnings)
    assert d.cancellation_clause.value is None


def test_retry_once_on_invalid_then_succeed():
    good = oracle_input(SAMPLES / "sample_a.pdf")
    bad = dict(good, price={"value": 1.0, "source_page": None, "source_quote": None})
    client = FakeClient(bad, good)
    d = run("sample_a.pdf", client)
    assert len(client.calls) == 2 and d.price.value == 2450000
    assert client.calls[1]["messages"][-1]["content"][0]["is_error"] is True


def test_fails_after_second_invalid():
    good = oracle_input(SAMPLES / "sample_a.pdf")
    bad = dict(good, price={"value": 1.0})
    with pytest.raises(ExtractionError):
        run("sample_a.pdf", FakeClient(bad, bad))


def test_fabricated_quote_is_flagged_and_wrong_page_is_corrected():
    inp = oracle_input(SAMPLES / "sample_a.pdf")
    inp["buyer"]["source_quote"] = "A name that is not in the document"
    inp["unit_id"]["source_page"] = 99
    d = run("sample_a.pdf", FakeClient(inp))
    assert any("'buyer'" in w and "not found" in w for w in d.warnings)
    assert d.unit_id.source_page != 99


def test_cache_hit_avoids_second_call():
    inp = oracle_input(SAMPLES / "sample_a.pdf")
    c1 = FakeClient(inp)
    run("sample_a.pdf", c1)
    c2 = FakeClient()  # would raise IndexError if called
    d = run("sample_a.pdf", c2)
    assert c2.calls == [] and d.file_hash


def test_cache_invalidated_when_model_changes(monkeypatch):
    inp = oracle_input(SAMPLES / "sample_a.pdf")
    run("sample_a.pdf", FakeClient(inp))
    monkeypatch.setattr(config, "MODEL", "another-model")  # model_tag() changes
    c = FakeClient(inp)
    run("sample_a.pdf", c)
    assert len(c.calls) == 1


def test_locate_quote_whitespace_insensitive():
    assert locate_quote(["foo  bar\nbaz"], "FOO bar baz") == 1
    assert normalize_text("It’s") == "it's"


def test_roundtrip_json():
    d = run("sample_c.pdf", FakeClient(oracle_input(SAMPLES / "sample_c.pdf")))
    assert ContractData.model_validate_json(d.model_dump_json()) == d


def test_quote_match_ignores_punctuation_but_not_fabrication():
    page = '(2) Layla Hassan, the individual identified in Schedule 1 (the "Buyer").\nBACKGROUND'
    assert locate_quote([page], "(2) Layla Hassan, the individual identified in Schedule 1 (the \u201cBuyer\u201d).") == 1
    assert locate_quote([page], "Layla Hassan the individual identified in Schedule 1 (the Buyer)") == 1
    assert locate_quote([page], "Layla Hassan, the corporate buyer of Schedule 1") is None
