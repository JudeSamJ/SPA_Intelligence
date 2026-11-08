"""Scanned PDFs through the real API: upload -> OCR -> extraction -> evidence, with fake OCR engines and a fake model."""
import hashlib
import json
import time

import pymupdf
import pytest

from app import ocr
from app.extract import pdf_pages
from app.llm import AnthropicAdapter
from app.ocr.types import OcrError
from backend.api import deps
from backend.tests.test_api import SAMPLES, FakeClient, client, env, oracle_input  # noqa: F401
from tests.test_ocr import SAMPLE, FakeEngine, make_scan

ORIGINAL = SAMPLE.read_bytes()


def upload(client, data, name="scan.pdf"):
    return client.post("/api/contracts/upload", files={"file": (name, data, "application/pdf")})


def wait(client, cid, want="extracted", timeout=20):
    seen, t0 = [], time.time()
    while time.time() - t0 < timeout:
        s = client.get(f"/api/contracts/{cid}/status").json()
        if not seen or seen[-1] != s["status"]:
            seen.append(s["status"])
        if s["status"] in (want, "error"):
            return s, seen
        time.sleep(0.02)
    return s, seen


@pytest.fixture
def with_ocr(monkeypatch):
    monkeypatch.setattr(ocr, "choose", lambda: (FakeEngine("docling", ORIGINAL), FakeEngine("qwen", ORIGINAL), ""))
    monkeypatch.setattr("app.extract.get_llm", lambda c=None: AnthropicAdapter(FakeClient(oracle_input(SAMPLE))))


def test_a_scanned_upload_is_read_extracted_and_keeps_its_id(client, env, with_ocr):
    scan = make_scan(ORIGINAL)
    cid = hashlib.sha256(scan).hexdigest()
    r = upload(client, scan)
    assert r.status_code == 202 and r.json()["id"] == cid
    s, seen = wait(client, cid)
    assert s["status"] == "extracted", s
    assert "ocr" in seen or "running" in seen
    # same id, a searchable working copy, and the user's original kept untouched
    work = env / "uploads" / f"{cid}.pdf"
    assert pdf_pages(work.read_bytes())[2].strip() and (env / "uploads" / "originals" / f"{cid}.pdf").read_bytes() == scan
    meta = json.loads((env / "uploads" / f"{cid}.meta.json").read_text())
    assert meta["id"] == cid and meta["ocr"]["engine"] == "docling" and meta["ocr"]["pages"] == [1, 2, 3, 4, 5, 6]
    d = client.get(f"/api/contracts/{cid}").json()
    assert d["contract"]["handover_date"]["value"] == "2027-06-30" and d["contract"]["handover_date"]["source_page"] == 3
    assert any("read from scanned images with docling and cross-checked with qwen" in w for w in d["contract"]["warnings"])
    # the evidence box works on the scan
    ev = client.get(f"/api/contracts/{cid}/evidence/handover_date").json()
    assert ev["evidence"]["bbox"] and ev["evidence"]["page"] == 3
    assert client.get(f"/api/contracts/{cid}/pdf").content.startswith(b"%PDF-")


def test_the_contract_id_survives_a_restart_with_the_searchable_file(client, env, with_ocr):
    scan = make_scan(ORIGINAL)
    cid = hashlib.sha256(scan).hexdigest()
    upload(client, scan)
    wait(client, cid)
    deps._hash_cache.clear()                                               # a restart: the registry is rebuilt from the files
    row = [c for c in client.get("/api/contracts").json() if c["name"] == "scan.pdf"]
    assert [r["id"] for r in row] == [cid] and row[0]["status"] == "extracted"


def test_ocr_that_fails_leaves_the_original_alone_and_reports_why(client, env, monkeypatch):
    monkeypatch.setattr(ocr, "choose", lambda: (FakeEngine("docling", ORIGINAL, fail=True), None, ""))
    scan = make_scan(ORIGINAL)
    cid = hashlib.sha256(scan).hexdigest()
    upload(client, scan)
    s, _ = wait(client, cid, "extracted")
    assert s["status"] == "error" and "boom" in s["error"]
    assert (env / "uploads" / f"{cid}.pdf").read_bytes() == scan and not (env / "uploads" / "originals").exists()


def test_without_ocr_a_scan_is_refused_with_a_reason(client, env, monkeypatch):
    monkeypatch.setattr(ocr, "choose", lambda: (None, None, "no OCR engine is available (docling: not installed; qwen: set QWEN_API_KEY and QWEN_MODEL)"))
    r = upload(client, make_scan(ORIGINAL))
    assert r.status_code == 422 and r.json()["error"]["code"] == "scanned_pdf"
    assert "No OCR engine is available" in r.json()["error"]["message"] and "QWEN_API_KEY" in r.json()["error"]["message"]


def test_a_blank_pdf_is_still_refused_even_when_ocr_is_on(client, env, with_ocr):
    d = pymupdf.open()
    d.new_page()
    assert upload(client, d.tobytes()).status_code == 422


def test_a_mixed_document_only_reads_its_scanned_pages(client, env, with_ocr):
    mixed = make_scan(ORIGINAL, only={2, 4})
    cid = hashlib.sha256(mixed).hexdigest()
    upload(client, mixed)
    s, _ = wait(client, cid)
    assert s["status"] == "extracted"
    meta = json.loads((env / "uploads" / f"{cid}.meta.json").read_text())
    assert meta["ocr"]["pages"] == [2, 4]
    c = client.get(f"/api/contracts/{cid}").json()["contract"]
    assert any("Pages 2, 4 were read from scanned images" in w for w in c["warnings"])


def test_a_garbled_page_sends_its_values_to_the_review_queue(client, env, monkeypatch):
    monkeypatch.setattr(ocr, "choose", lambda: (FakeEngine("docling", ORIGINAL), FakeEngine("qwen", ORIGINAL, garble={3}), ""))
    monkeypatch.setattr("app.extract.get_llm", lambda c=None: AnthropicAdapter(FakeClient(oracle_input(SAMPLE))))
    scan = make_scan(ORIGINAL)
    cid = hashlib.sha256(scan).hexdigest()
    upload(client, scan)
    wait(client, cid)
    q = client.get("/api/review-queue").json()["items"]
    mine = [i for i in q if i["contract_id"] == cid and i["field"] == "handover_date"]
    assert mine and any("read by OCR" in r for r in mine[0]["reasons"])


def test_health_reports_whether_scan_reading_is_on(client, monkeypatch):
    monkeypatch.setattr(ocr, "choose", lambda: (None, None, "off"))
    assert client.get("/api/health").json()["ocr"] == {"enabled": False, "engine": None, "verified": False}
    monkeypatch.setattr(ocr, "choose", lambda: (FakeEngine("qwen", ORIGINAL), FakeEngine("docling", ORIGINAL), ""))
    assert client.get("/api/health").json()["ocr"] == {"enabled": True, "engine": "qwen", "verified": True}


def test_a_normal_pdf_never_touches_ocr(client, env, monkeypatch):
    monkeypatch.setattr(ocr, "make_searchable", lambda *a, **k: pytest.fail("OCR must not run on a text PDF"))
    monkeypatch.setattr(ocr, "choose", lambda: (FakeEngine("docling", ORIGINAL), None, ""))
    monkeypatch.setattr("app.extract.get_llm", lambda c=None: AnthropicAdapter(FakeClient(oracle_input(SAMPLE))))
    cid = hashlib.sha256(ORIGINAL).hexdigest()
    upload(client, ORIGINAL, "text.pdf")
    s, _ = wait(client, cid)
    assert s["status"] == "extracted" and not (env / "uploads" / "originals").exists()
