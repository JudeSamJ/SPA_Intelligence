"""Grounding + evidence boxes. Uses the real sample PDFs; the 'model output' is the test oracle."""
import copy
from datetime import date
from pathlib import Path

import pytest

from app.evidence import locate
from app.extract import extract_from_llm, pdf_pages, postprocess
from app.grounding import parse_dates, parse_numbers
from app.schema import ContractData
from tests.fakes import FakeClient, oracle_input

A = Path("samples/sample_a.pdf")


def contract_from(inp: dict, path: Path = A) -> ContractData:
    b = path.read_bytes()
    out = extract_from_llm(b, FakeClient(inp))
    return postprocess(ContractData(**out.model_dump()), pdf_pages(b), b)


def test_all_good_fields_grounded_with_boxes():
    c = contract_from(oracle_input(A))
    for n in ("buyer", "unit_id", "price", "area_sqft", "handover_date", "delay_rate", "delay_cap"):
        it = getattr(c, n)
        assert it.grounding.status == "grounded", n
        assert it.confidence == 1.0 and not it.needs_review
        assert it.evidence.bbox and len(it.evidence.bbox) == 4 and it.evidence.method == "exact"
    assert all(m.grounding.status == "grounded" and m.evidence.bbox for m in c.payment_plan)
    assert len(c.payment_plan) == 5 and c.payment_plan_percent_sum == 100


def test_wrong_quote_is_ungrounded_value_null_and_warned():
    inp = oracle_input(A)
    inp["price"]["source_quote"] = "AED 9,999,999 payable in full on the moon"
    c = contract_from(inp)
    assert c.price.value is None
    assert c.price.grounding.status == "ungrounded"
    assert c.price.grounding.claimed_value == "2450000.0"
    assert c.price.needs_review and c.price.evidence.bbox is None
    assert any("'price' is ungrounded" in w for w in c.warnings)


def test_value_not_in_quote_is_ungrounded():
    """Quote is real (exists on the page) but the claimed number is not in it."""
    inp = oracle_input(A)
    inp["price"]["value"] = 3_000_000.0
    c = contract_from(inp)
    assert c.price.grounding.status == "ungrounded"
    assert c.price.value is None
    assert any(not ch.passed and ch.name == "value_in_quote" for ch in c.price.grounding.checks)


def test_entity_not_in_document_is_ungrounded():
    inp = oracle_input(A)
    inp["buyer"]["value"] = "Zed Nonexistent"
    c = contract_from(inp)
    assert c.buyer.value is None and c.buyer.grounding.status == "ungrounded"


def test_wrong_page_is_corrected_and_not_a_failure():
    inp = oracle_input(A)
    real = inp["handover_date"]["source_page"]
    inp["handover_date"]["source_page"] = real + 1 if real < 6 else real - 1
    c = contract_from(inp)
    assert c.handover_date.source_page == real
    assert c.handover_date.grounding.status == "grounded"


def test_fuzzy_quote_is_partial_and_needs_review():
    inp = oracle_input(A)
    q = inp["delay_cap"]["source_quote"]
    inp["delay_cap"]["source_quote"] = q.replace("shall not exceed", "shall never exceed")
    c = contract_from(inp)
    assert c.delay_cap.grounding.status == "partial"
    assert c.delay_cap.needs_review and c.delay_cap.value == 10.0 and c.delay_cap.confidence < 1


def test_ungrounded_payment_row_is_excluded():
    inp = oracle_input(A)
    inp["payment_plan"][0]["source_quote"] = "Booking made-up row 99% sometime"
    c = contract_from(inp)
    assert len(c.payment_plan) == 4 and len(c.ungrounded_rows) == 1
    assert c.payment_plan_percent_sum == 80
    assert any("excluded" in w for w in c.warnings)


def test_tool_schema_hides_trust_fields():
    from app.extract import _tool_schema
    import json
    txt = json.dumps(_tool_schema())
    for f in ("grounding", "needs_review", "human_verified", "bbox"):
        assert f not in txt


def test_parsers_numeric_not_string():
    assert 2450000.0 in parse_numbers("AED 2,450,000")
    assert 2450000.0 in parse_numbers("AED 2.45 million")
    assert 6.0 in parse_numbers("6% per annum") and 60.0 in parse_numbers("sixty (60) days")
    assert date(2027, 6, 30) in parse_dates("30th June 2027")
    assert date(2027, 6, 30) in parse_dates("June 30, 2027")
    assert date(2027, 6, 30) in parse_dates("30/06/2027") and date(2027, 6, 30) in parse_dates("2027-06-30")


def test_locate_handles_missing_quote():
    ev = locate(A.read_bytes(), 1, "this sentence is nowhere in the file")
    assert ev.bbox is None and ev.method == "not_found"


def test_locate_returns_line_rects_for_multiline_quote():
    c = contract_from(oracle_input(A))
    ev = c.delay_cap.evidence
    assert ev.rects and ev.bbox[2] - ev.bbox[0] > 100
