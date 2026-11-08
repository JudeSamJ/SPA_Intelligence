"""The scanned-PDF path with REAL OCR (Tesseract, behind a stand-in Qwen endpoint) over real HTTP. Skipped when Tesseract is absent.

Unlike the fake-engine tests, the recognised text here has genuine OCR errors and the boxes are real, so this shows how grounding,
review flags and evidence highlights behave on imperfect OCR. It proves the pipeline, NOT Qwen's own accuracy."""
import os

import pytest

from app import ocr
from app.evidence import locate
from app.extract import extract_contract, pdf_pages
from app.ocr import qwen_engine
from app.ocr.qwen_engine import QwenOcr
from tests import tesseract_server
from tests.fakes import FakeClient, oracle_input
from tests.test_ocr import SAMPLE, make_scan

pytestmark = pytest.mark.skipif(not tesseract_server.AVAILABLE, reason="tesseract is not installed")


@pytest.fixture(scope="module")
def server():
    srv, base = tesseract_server.start()
    yield srv, base
    srv.shutdown()


@pytest.fixture
def qwen_env(monkeypatch, server):
    srv, base = server
    srv.seen.clear()
    monkeypatch.setenv("QWEN_BASE_URL", base)
    monkeypatch.setenv("QWEN_API_KEY", "k" * 20)
    monkeypatch.setenv("QWEN_MODEL", "qwen-vl-standin")
    monkeypatch.setenv("OCR_ENGINE", "qwen")
    monkeypatch.setenv("OCR_VERIFY", "0")
    monkeypatch.setattr(ocr, "_engines", lambda: {"docling": type("D", (), {"name": "docling", "available": lambda s: (False, "no")})(), "qwen": QwenOcr()})
    qwen_engine._calls = 0


def test_real_ocr_over_http_makes_a_scan_searchable_and_extractable(qwen_env, server):
    original = SAMPLE.read_bytes()
    scan = make_scan(original)
    assert all(not t.strip() for t in pdf_pages(scan))
    layered, rep = ocr.make_searchable(scan)
    assert rep["engine"] == "qwen" and sorted(rep["pages"]) == ["1", "2", "3", "4", "5", "6"] and rep["unread"] == []
    assert len(server[0].seen) == 6 and server[0].seen[0] == {"auth": "Bearer " + "k" * 20, "model": "qwen-vl-standin"}
    text = " ".join(pdf_pages(layered)).lower()
    for phrase in ("handover date", "grace period", "notice of completion", "purchase price"):
        assert phrase in text, phrase                                  # real OCR recovered the contract's own words
    assert all(v["coarse"] is False for v in rep["pages"].values())    # positions were usable, scaled from pixels to points


def test_evidence_boxes_on_real_ocr_land_where_the_text_is(qwen_env):
    original = SAMPLE.read_bytes()
    layered, _ = ocr.make_searchable(make_scan(original))
    quote = "The Seller shall complete construction of the Unit and serve the Notice of Completion on or before 30 June 2027"
    truth, got = locate(original, 3, quote), locate(layered, 3, quote)
    assert got.method in ("exact", "fuzzy") and got.bbox, got                # found despite OCR errors
    a, b = truth.bbox, got.bbox
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    assert inter / union > 0.4, (a, b)                                       # the highlight is on the right words


def test_the_full_pipeline_on_real_ocr_grounds_the_key_values_and_flags_them_as_unverified(qwen_env):
    from app.review import review_items
    original = SAMPLE.read_bytes()
    layered, rep = ocr.make_searchable(make_scan(original))
    c = extract_contract(layered, "scan.pdf", client=FakeClient(oracle_input(SAMPLE)), use_cache=False)
    assert c.handover_date.value.isoformat() == "2027-06-30" and c.handover_date.source_page == 3
    assert c.handover_date.grounding.status in ("grounded", "partial") and c.handover_date.evidence.bbox
    assert c.price.value == 2450000 and c.price.grounding.status in ("grounded", "partial")
    assert any("read from scanned images with qwen (no second reading to compare)" in w for w in c.warnings)
    # one engine only: nothing to cross-check, so every OCR-derived value is routed to a human by default
    assert c.handover_date.needs_review and "handover_date" in {i["field"] for i in review_items(c)}
