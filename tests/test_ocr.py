"""Scanned-PDF support. The OCR engines are fakes or mock HTTP (no model, no network); everything else is real: real scanned-image PDFs,
real invisible text layers, the real evidence boxes, grounding and extraction."""
import json
import os
from pathlib import Path

import httpx
import pymupdf
import pytest

from app import ocr
from app.evidence import locate
from app.extract import extract_contract, pdf_pages
from app.ocr import qwen_engine
from app.ocr.qwen_engine import QwenOcr, parse_reply
from app.ocr.textlayer import add_text_layer, read_report
from app.ocr.types import OcrEngine, OcrError, OcrLine, OcrPage
from app.ocr.verify import agreement
from tests.fakes import FakeClient, oracle_input

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "samples" / "sample_a.pdf"


def make_scan(pdf_bytes: bytes, only: set[int] | None = None) -> bytes:
    """Replace the chosen pages (default all) with a picture of themselves: a genuine scanned PDF, no text layer."""
    src = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    out = pymupdf.open()
    for i, page in enumerate(src, 1):
        if only is not None and i not in only:
            out.insert_pdf(src, from_page=i - 1, to_page=i - 1)
            continue
        jpg = page.get_pixmap(dpi=150, alpha=False).tobytes("jpeg", jpg_quality=70)     # real scans are JPEG pictures of the page
        np_ = out.new_page(width=page.rect.width, height=page.rect.height)
        np_.insert_image(np_.rect, stream=jpg)
    return out.tobytes()


def true_lines(pdf_bytes: bytes, page_no: int) -> OcrPage:
    """What a perfect OCR would return for a page: the real lines and their real positions."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_no - 1]
        op = OcrPage(page_no, float(page.rect.width), float(page.rect.height), engine="fake")
        for b in page.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = "".join(s["text"] for s in ln["spans"]).strip()
                if t:
                    op.lines.append(OcrLine(t, tuple(ln["bbox"])))
        return op


class FakeEngine(OcrEngine):
    """Reads the pages from the ORIGINAL text PDF it was given; optionally corrupts some pages to simulate bad OCR."""

    def __init__(self, name, original, ok=True, garble=(), fail=False, skip=(), swap=None):
        self.name, self.original, self.ok, self.garble, self.fail, self.skip = name, original, ok, set(garble), fail, set(skip)
        self.swap = swap or {}                                           # {page: (old, new)}: one misread digit, like real OCR

    def available(self):
        return (self.ok, "" if self.ok else "not installed")

    def read_pages(self, pdf_bytes, pages):
        if self.fail:
            raise OcrError("boom")
        out = {}
        for p in pages:
            if p in self.skip:
                continue
            op = true_lines(self.original, p)
            op.engine = self.name
            if p in self.garble:
                op.lines = [OcrLine("zq xv " + l.text[::-1], l.bbox) for l in op.lines]
            if p in self.swap:
                old, new = self.swap[p]
                op.lines = [OcrLine(l.text.replace(old, new), l.bbox) for l in op.lines]
            out[p] = op
        return out


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("OCR_ENGINE", "OCR_VERIFY", "OCR_MAX_PAGES", "OCR_MIN_CHARS", "OCR_AGREEMENT_MIN", "OCR_REVIEW_UNVERIFIED", "QWEN_API_KEY",
              "QWEN_MODEL", "QWEN_BASE_URL", "QWEN_BBOX_MODE", "OCR_MAX_CALLS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OCR_RETRY_SLEEP", "0")
    qwen_engine._calls = 0
    yield


@pytest.fixture
def original():
    return SAMPLE.read_bytes()


def use(monkeypatch, primary, verifier=None):
    monkeypatch.setattr(ocr, "choose", lambda: (primary, verifier, ""))


# ------------------------------------------------------------------ detecting scans
def test_text_pdfs_scans_and_mixed_documents_are_told_apart(original):
    n = pymupdf.open(stream=original, filetype="pdf").page_count
    assert ocr.pages_needing_ocr(original) == []
    assert ocr.pages_needing_ocr(make_scan(original)) == list(range(1, n + 1))
    assert ocr.pages_needing_ocr(make_scan(original, only={2, 4})) == [2, 4]          # only the scanned pages pay for OCR


def test_a_blank_page_is_not_sent_to_ocr():
    d = pymupdf.open()
    d.new_page()
    assert ocr.pages_needing_ocr(d.tobytes()) == []


# ------------------------------------------------------------------ the invisible text layer
def test_text_layer_makes_a_scan_searchable_without_changing_how_it_looks(original):
    scan = make_scan(original)
    assert all(len(t.strip()) == 0 for t in pdf_pages(scan))
    layered = add_text_layer(scan, {p: true_lines(original, p) for p in range(1, 7)}, {"v": 1})
    assert pdf_pages(layered)[2].split() == pdf_pages(original)[2].split() or "Handover Date" in pdf_pages(layered)[2]
    a, b = pymupdf.open(stream=scan, filetype="pdf"), pymupdf.open(stream=layered, filetype="pdf")
    for i in range(a.page_count):
        assert a[i].get_pixmap(dpi=72).samples == b[i].get_pixmap(dpi=72).samples        # the text is invisible: pixels identical


def test_evidence_boxes_land_on_the_real_text_of_a_scanned_page(original):
    quote = "The Seller shall complete construction of the Unit and serve the Notice of Completion on or before 30 June 2027"
    layered = add_text_layer(make_scan(original), {p: true_lines(original, p) for p in range(1, 7)})
    ev_true, ev_scan = locate(original, 3, quote), locate(layered, 3, quote)
    assert ev_true.method == "exact" and ev_scan.method in ("exact", "fuzzy") and ev_scan.bbox
    a, b = ev_true.bbox, ev_scan.bbox
    inter = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    assert inter / union > 0.5, (a, b)                                                    # the highlight sits where the words really are


def test_typographic_punctuation_survives_for_quote_matching():
    d = pymupdf.open()
    d.new_page().insert_image(pymupdf.Rect(0, 0, 100, 100), stream=pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 8, 8), False).tobytes("png"))
    op = OcrPage(1, 595.0, 842.0, [OcrLine("The “Handover Date” — 30 June 2027…", (50, 100, 500, 120))])
    text = pdf_pages(add_text_layer(d.tobytes(), {1: op}))[0]
    assert '"Handover Date"' in text and "30 June 2027" in text


def test_report_roundtrip_and_ordinary_pdfs_have_none(original):
    assert read_report(original) is None
    layered = add_text_layer(make_scan(original), {1: true_lines(original, 1)}, {"v": 1, "engine": "x", "pages": {"1": {"low": False}}})
    assert read_report(layered)["engine"] == "x"
    assert read_report(b"not a pdf") is None


# ------------------------------------------------------------------ choosing engines
def test_engine_choice(monkeypatch, original):
    ok, missing = FakeEngine("docling", original), FakeEngine("qwen", original, ok=False)
    monkeypatch.setattr(ocr, "_engines", lambda: {"docling": ok, "qwen": missing})
    p, v, why = ocr.choose()
    assert p.name == "docling" and v is None                                              # the other engine is not available: no verifier
    monkeypatch.setattr(ocr, "_engines", lambda: {"docling": ok, "qwen": FakeEngine("qwen", original)})
    p, v, _ = ocr.choose()
    assert (p.name, v.name) == ("docling", "qwen")
    monkeypatch.setenv("OCR_VERIFY", "0")
    assert ocr.choose()[1] is None
    monkeypatch.delenv("OCR_VERIFY")
    monkeypatch.setenv("OCR_ENGINE", "qwen")
    assert ocr.choose()[0].name == "qwen" and ocr.choose()[1].name == "docling"
    monkeypatch.setenv("OCR_ENGINE", "none")
    assert ocr.choose()[0] is None and not ocr.enabled()
    monkeypatch.setenv("OCR_ENGINE", "bogus")
    assert "unknown OCR_ENGINE" in ocr.choose()[2]
    monkeypatch.setenv("OCR_ENGINE", "auto")
    monkeypatch.setattr(ocr, "_engines", lambda: {"docling": missing, "qwen": missing})
    assert ocr.choose()[0] is None and "no OCR engine is available" in ocr.choose()[2]


# ------------------------------------------------------------------ verification and flags
def test_two_agreeing_readings_pass_and_a_garbled_page_is_flagged(monkeypatch, original):
    scan = make_scan(original)
    use(monkeypatch, FakeEngine("docling", original), FakeEngine("qwen", original, garble={3}))
    layered, rep = ocr.make_searchable(scan)
    assert rep["engine"] == "docling" and rep["verifier"] == "qwen"
    assert rep["pages"]["3"]["low"] is True and rep["pages"]["3"]["agree"] < 0.8
    assert all(not v["low"] and v["agree"] == 1.0 for k, v in rep["pages"].items() if k != "3")
    assert read_report(layered) == rep
    assert pdf_pages(scan) == [""] * 6                                                      # the input was not modified


def test_unverified_pages_go_to_review_unless_switched_off(monkeypatch, original):
    use(monkeypatch, FakeEngine("qwen", original))
    _, rep = ocr.make_searchable(make_scan(original))
    assert rep["verifier"] is None and all(v["low"] and v["agree"] is None for v in rep["pages"].values())
    monkeypatch.setenv("OCR_REVIEW_UNVERIFIED", "0")
    _, rep = ocr.make_searchable(make_scan(original))
    assert not any(v["low"] for v in rep["pages"].values())


def test_a_failed_second_opinion_keeps_the_first_reading(monkeypatch, original):
    use(monkeypatch, FakeEngine("docling", original), FakeEngine("qwen", original, fail=True))
    layered, rep = ocr.make_searchable(make_scan(original))
    assert rep["verifier"] is None and "verification failed" in rep["note"] and len(rep["pages"]) == 6


def test_pages_the_engine_could_not_read_are_reported(monkeypatch, original):
    use(monkeypatch, FakeEngine("docling", original, skip={5}))
    _, rep = ocr.make_searchable(make_scan(original))
    assert rep["unread"] == [5] and "5" not in rep["pages"]


def test_limits_and_failures_are_readable_errors(monkeypatch, original):
    scan = make_scan(original)
    use(monkeypatch, FakeEngine("docling", original))
    monkeypatch.setenv("OCR_MAX_PAGES", "3")
    with pytest.raises(OcrError, match="limit is 3"):
        ocr.make_searchable(scan)
    monkeypatch.delenv("OCR_MAX_PAGES")
    with pytest.raises(OcrError, match="no scanned pages"):
        ocr.make_searchable(original)
    use(monkeypatch, FakeEngine("docling", original, skip={1, 2, 3, 4, 5, 6}))
    with pytest.raises(OcrError, match="could not read any text"):
        ocr.make_searchable(scan)
    monkeypatch.setattr(ocr, "choose", lambda: (None, None, "OCR is switched off"))
    with pytest.raises(OcrError, match="switched off"):
        ocr.make_searchable(scan)


# ------------------------------------------------------------------ the whole pipeline on a scan
def test_a_scanned_contract_extracts_grounds_and_highlights_like_a_normal_one(monkeypatch, original):
    use(monkeypatch, FakeEngine("docling", original), FakeEngine("qwen", original))
    layered, rep = ocr.make_searchable(make_scan(original))
    c = extract_contract(layered, "scan.pdf", client=FakeClient(oracle_input(SAMPLE)), use_cache=False)
    assert c.handover_date.value.isoformat() == "2027-06-30" and c.handover_date.source_page == 3
    assert c.handover_date.grounding.status in ("grounded", "partial") and c.handover_date.evidence.bbox
    assert any("read from scanned images with docling and cross-checked with qwen" in w for w in c.warnings)
    assert not any(it.get("reasons") and any("OCR" in r for r in it["reasons"]) for it in __import__("app.review", fromlist=["x"]).review_items(c))


def test_values_from_a_page_the_two_readers_disagree_on_go_to_review(monkeypatch, original):
    from app.review import review_items
    use(monkeypatch, FakeEngine("docling", original), FakeEngine("qwen", original, garble={3}))
    layered, _ = ocr.make_searchable(make_scan(original))
    c = extract_contract(layered, "scan.pdf", client=FakeClient(oracle_input(SAMPLE)), use_cache=False)
    assert any("Pages 3 need a human check: the two readings disagree" in w for w in c.warnings)
    assert c.handover_date.needs_review and c.handover_date.confidence <= 0.7
    flagged = {it["field"] for it in review_items(c)}
    assert "handover_date" in flagged
    reason = [it for it in review_items(c) if it["field"] == "handover_date"][0]["reasons"]
    assert any("page 3 was read by OCR and the two readings agree only" in r for r in reason)
    assert not c.price.needs_review or c.price.source_page == 3                             # other pages were not touched


def test_an_ordinary_pdf_is_untouched_by_ocr_flags(original):
    c = extract_contract(original, "a.pdf", client=FakeClient(oracle_input(SAMPLE)), use_cache=False)
    assert not any("scanned" in w for w in c.warnings)


# ------------------------------------------------------------------ agreement
def test_agreement_scores():
    assert agreement("The Seller shall pay 6% per annum", "the seller shall pay 6% per annum.") == 1.0
    assert agreement("", "") == 1.0 and agreement("text", "") == 0.0
    assert agreement("The Seller shall pay 6% per annum", "The Seller shall pay 8% per annum") < 1.0
    assert agreement("The Seller shall pay interest at six percent per annum", "Buyer must inspect the property within fourteen days") < 0.6


# ------------------------------------------------------------------ Qwen: reply parsing
LINES = {"lines": [{"text": "Handover Date", "bbox": [100, 200, 700, 260]}, {"text": "30 June 2027", "bbox": [100, 300, 500, 360]}]}


def test_pixel_coordinates_are_scaled_to_points():
    full_page = {"lines": LINES["lines"] + [{"text": "footer", "bbox": [100, 2200, 700, 2260]}]}   # a real page reaches the bottom
    p = parse_reply(json.dumps(full_page), 1, 1654, 2339, 595.0, 842.0)                     # A4 at 200 dpi
    assert not p.coarse and p.lines[0].text == "Handover Date"
    assert p.lines[0].bbox == pytest.approx((100 * 595 / 1654, 200 * 842 / 2339, 700 * 595 / 1654, 260 * 842 / 2339))


def test_relative_1000_coordinates_are_recognised_automatically():
    rel = {"lines": [{"text": "x", "bbox": [100, 200, 500, 250]}, {"text": "y", "bbox": [100, 900, 500, 980]}]}
    p = parse_reply(json.dumps(rel), 1, 1654, 2339, 595.0, 842.0)
    assert p.lines[1].bbox == pytest.approx((59.5, 757.8, 297.5, 825.16))


def test_a_sparse_page_is_ambiguous_so_the_mode_can_be_pinned(monkeypatch):
    """Short pixel coordinates look like relative ones. QWEN_BBOX_MODE=pixels removes the doubt for a model that reports pixels."""
    monkeypatch.setenv("QWEN_BBOX_MODE", "pixels")
    p = parse_reply(json.dumps(LINES), 1, 1654, 2339, 595.0, 842.0)
    assert p.lines[0].bbox == pytest.approx((100 * 595 / 1654, 200 * 842 / 2339, 700 * 595 / 1654, 260 * 842 / 2339))


def test_bbox_mode_can_be_forced(monkeypatch):
    rel = {"lines": [{"text": "x", "bbox": [100, 200, 500, 250]}]}
    monkeypatch.setenv("QWEN_BBOX_MODE", "pixels")
    assert parse_reply(json.dumps(rel), 1, 1654, 2339, 595.0, 842.0).lines[0].bbox[0] == pytest.approx(100 * 595 / 1654)


def test_fences_prose_and_junk_lines_are_tolerated():
    reply = "Here you go:\n```json\n" + json.dumps({"lines": LINES["lines"] + [{"text": "", "bbox": [1, 2, 3, 4]}, {"nope": 1}, "str"]}) + "\n```"
    assert [l.text for l in parse_reply(reply, 1, 1654, 2339, 595.0, 842.0).lines] == ["Handover Date", "30 June 2027"]


def test_missing_positions_fall_back_to_coarse_bands_and_keep_the_text():
    p = parse_reply(json.dumps({"lines": [{"text": "one"}, {"text": "two"}, {"text": "three"}]}), 1, 1654, 2339, 595.0, 842.0)
    assert p.coarse and [l.text for l in p.lines] == ["one", "two", "three"]
    assert p.lines[0].bbox[1] < p.lines[1].bbox[1] < p.lines[2].bbox[1] and all(l.bbox[3] <= 842 for l in p.lines)


def test_nonsense_positions_are_dropped():
    bad = {"lines": [{"text": "off page", "bbox": [5000, 5000, 6000, 6000]}, {"text": "inverted", "bbox": [300, 300, 100, 100]}]}
    p = parse_reply(json.dumps(bad), 1, 1654, 2339, 595.0, 842.0)
    assert p.coarse and len(p.lines) == 2                                                   # text kept, placed in bands


@pytest.mark.parametrize("junk", ["", "no json here", "{not json}", '{"lines": 3}', "[1,2]"])
def test_unusable_replies_raise(junk):
    with pytest.raises(OcrError):
        parse_reply(junk, 1, 1654, 2339, 595.0, 842.0)


# ------------------------------------------------------------------ Qwen: the HTTP call
class Server:
    def __init__(self, reply=None, status=200):
        self.reply, self.status, self.requests = reply if reply is not None else json.dumps(LINES), status, []

    def __call__(self, request: httpx.Request):
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "x"})
        return httpx.Response(200, json={"choices": [{"message": {"content": self.reply}}]})


@pytest.fixture
def qwen(monkeypatch):
    monkeypatch.setenv("QWEN_API_KEY", "k" * 20)
    monkeypatch.setenv("QWEN_MODEL", "qwen-vl-test")
    s = Server()
    monkeypatch.setattr(QwenOcr, "TRANSPORT", httpx.MockTransport(s))
    return s


def test_qwen_needs_a_key_a_model_and_a_safe_url(monkeypatch):
    e = QwenOcr()
    assert e.available() == (False, "set QWEN_API_KEY and QWEN_MODEL")
    monkeypatch.setenv("QWEN_API_KEY", "k" * 20)
    monkeypatch.setenv("QWEN_MODEL", "m")
    assert e.available() == (True, "")
    monkeypatch.setenv("QWEN_BASE_URL", "http://example.com/v1")
    assert not e.available()[0]
    monkeypatch.setenv("QWEN_BASE_URL", "http://localhost:11434/v1")
    assert e.available()[0]


def test_qwen_sends_each_page_image_with_the_model_and_key(qwen, original):
    out = QwenOcr().read_pages(make_scan(original), [2, 3])
    assert sorted(out) == [2, 3] and out[2].lines[0].text == "Handover Date" and out[2].engine == "qwen"
    assert len(qwen.requests) == 2
    r = qwen.requests[0]
    body = json.loads(r.content)
    assert str(r.url).endswith("/chat/completions") and r.headers["authorization"] == "Bearer " + "k" * 20
    assert body["model"] == "qwen-vl-test" and body["temperature"] == 0
    content = body["messages"][0]["content"]
    assert content[1]["image_url"]["url"].startswith("data:image/png;base64,") and "OCR engine" in content[0]["text"]


def test_a_refused_key_stops_at_once_with_a_clear_message(monkeypatch, original):
    s = Server(status=401)
    monkeypatch.setenv("QWEN_API_KEY", "k" * 20)
    monkeypatch.setenv("QWEN_MODEL", "m")
    monkeypatch.setattr(QwenOcr, "TRANSPORT", httpx.MockTransport(s))
    with pytest.raises(OcrError, match="check QWEN_API_KEY"):
        QwenOcr().read_pages(make_scan(original), [1, 2, 3])
    assert len(s.requests) <= 3                                                             # no retry storm on a wrong key


def test_server_errors_are_retried_then_that_page_is_skipped(monkeypatch, original):
    s = Server(status=500)
    monkeypatch.setenv("QWEN_API_KEY", "k" * 20)
    monkeypatch.setenv("QWEN_MODEL", "m")
    monkeypatch.setattr(QwenOcr, "TRANSPORT", httpx.MockTransport(s))
    with pytest.raises(OcrError, match="did not answer \\(HTTP 500\\)"):                  # every page failed: the reason is reported
        QwenOcr().read_pages(make_scan(original), [1])
    assert len(s.requests) == 3


def test_a_page_with_an_unreadable_reply_is_skipped_not_fatal(monkeypatch, original):
    monkeypatch.setenv("QWEN_API_KEY", "k" * 20)
    monkeypatch.setenv("QWEN_MODEL", "m")
    monkeypatch.setattr(QwenOcr, "TRANSPORT", httpx.MockTransport(Server(reply="sorry, I cannot")))
    with pytest.raises(OcrError, match="not JSON"):
        QwenOcr().read_pages(make_scan(original), [1, 2])                                   # nothing readable at all: say why
    replies = iter(["garbage", json.dumps(LINES)])                                        # first page unreadable, second fine
    monkeypatch.setattr(QwenOcr, "TRANSPORT", httpx.MockTransport(
        lambda r: httpx.Response(200, json={"choices": [{"message": {"content": next(replies)}}]})))
    monkeypatch.setenv("OCR_WORKERS", "1")
    assert len(QwenOcr().read_pages(make_scan(original), [1, 2])) == 1                    # one page failing does not lose the others


def test_the_call_cap_protects_the_key(monkeypatch, original, qwen):
    monkeypatch.setenv("OCR_MAX_CALLS", "2")
    with pytest.raises(OcrError, match="call cap reached"):
        QwenOcr().read_pages(make_scan(original), [1, 2, 3, 4])


def test_the_api_key_is_never_in_an_error_message(monkeypatch, original):
    monkeypatch.setenv("QWEN_API_KEY", "secret-key-value-123456")
    monkeypatch.setenv("QWEN_MODEL", "m")
    monkeypatch.setattr(QwenOcr, "TRANSPORT", httpx.MockTransport(Server(status=401)))
    with pytest.raises(OcrError) as e:
        QwenOcr().read_pages(make_scan(original), [1])
    assert "secret-key-value" not in str(e.value)


# ------------------------------------------------------------------ numbers are compared on their own
def test_number_comparison_catches_one_wrong_digit_that_a_page_score_would_miss():
    from app.ocr.verify import number_differences, numbers
    a = "The Seller shall pay interest at 6% per annum on the Purchase Price of AED 2,450,000 by 30 June 2027. " * 3 + "word " * 150
    b = a.replace("6% per", "8% per")
    assert agreement(a, b) > 0.97                                                  # the page score barely moves...
    assert number_differences(a, b) == ["6", "8"]                                  # ...but the numbers disagree
    assert numbers("AED 2,450,000.00 and 1,000 and 30.5") == {"2450000.00", "1000", "30.5"}
    assert number_differences("Due 30 June 2027", "Due 30 June 2O27") == ["2", "2027", "27"]


def test_a_misread_digit_flags_only_the_values_that_quote_it(monkeypatch, original):
    from app.review import review_items
    use(monkeypatch, FakeEngine("docling", original), FakeEngine("qwen", original, swap={3: ("2027", "2O27")}))
    layered, rep = ocr.make_searchable(make_scan(original))
    assert rep["pages"]["3"]["low"] is False and rep["pages"]["3"]["agree"] > 0.9 and rep["pages"]["3"]["num_diff"]
    c = extract_contract(layered, "scan.pdf", client=FakeClient(oracle_input(SAMPLE)), use_cache=False)
    flagged = {i["field"]: i for i in review_items(c)}
    assert "handover_date" in flagged                                              # its quote contains the disputed number
    assert any("differ on a number" in r for r in flagged["handover_date"]["reasons"])
    assert "buyer" not in flagged and "unit_id" not in flagged                     # other values are left alone
    assert any("differ on numbers on pages 3" in w for w in c.warnings)
