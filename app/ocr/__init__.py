"""Scanned PDF support: read image pages with OCR, then add the text back as an invisible layer so the rest of the app works unchanged.

Engines (both optional):
  docling  open-source parser with its own OCR; heavy (PyTorch), best positions. Run it where there is memory.
  qwen     a Qwen vision model through an API; light, works on small hosts.
When both are available they CROSS-CHECK each page: if the two readings disagree, values from that page are sent to human review.
With only one engine the pages are "unverified" and (by default) also go to review. Nothing here is silent: every OCR'd page is
named in the contract's warnings.

Settings: OCR_ENGINE=auto|docling|qwen|none (default auto), OCR_VERIFY=1, OCR_MAX_PAGES=40, OCR_DPI=200, OCR_AGREEMENT_MIN=0.80,
OCR_MIN_CHARS=25, OCR_REVIEW_UNVERIFIED=1, OCR_WORKERS=3, OCR_MAX_CALLS=300.
"""
from __future__ import annotations

import os

import pymupdf

from .docling_engine import DoclingOcr
from .qwen_engine import QwenOcr
from .textlayer import add_text_layer, read_report
from .types import OcrEngine, OcrError, OcrPage
from .verify import agreement, number_differences, numbers

__all__ = ["OcrError", "pages_needing_ocr", "engines_status", "enabled", "make_searchable", "read_report", "apply_flags", "choose"]


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name) or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name) or default)
    except ValueError:
        return default


def pages_needing_ocr(pdf_bytes: bytes) -> list[int]:
    """1-based pages that carry an image but almost no text (scans). Blank pages and normal text pages are left alone, so a mixed
    document only pays for the pages that need it."""
    min_chars = _env_int("OCR_MIN_CHARS", 25)
    out = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for i, page in enumerate(doc, 1):
            if len(page.get_text().strip()) < min_chars and page.get_images(full=True):
                out.append(i)
    return out


def _engines() -> dict[str, OcrEngine]:
    return {"docling": DoclingOcr(), "qwen": QwenOcr()}


def engines_status() -> dict[str, dict]:
    return {n: dict(zip(("available", "reason"), e.available())) for n, e in _engines().items()}


def choose() -> tuple[OcrEngine | None, OcrEngine | None, str]:
    """(primary, verifier, why-not). The verifier is the other engine when it is available and verification is on."""
    mode = (os.environ.get("OCR_ENGINE") or "auto").strip().lower()
    if mode == "none":
        return None, None, "OCR is switched off (OCR_ENGINE=none)"
    engs = _engines()
    order = ["docling", "qwen"] if mode == "auto" else [mode] if mode in engs else []
    if not order:
        return None, None, f"unknown OCR_ENGINE '{mode}' (use auto, docling, qwen or none)"
    primary = next((engs[n] for n in order if engs[n].available()[0]), None)
    if primary is None:
        why = "; ".join(f"{n}: {engs[n].available()[1]}" for n in order)
        return None, None, "no OCR engine is available (" + why + ")"
    other = engs["qwen" if primary.name == "docling" else "docling"]
    verifier = other if os.environ.get("OCR_VERIFY", "1") != "0" and other.available()[0] else None
    return primary, verifier, ""


def enabled() -> bool:
    return choose()[0] is not None


def make_searchable(pdf_bytes: bytes) -> tuple[bytes, dict]:
    """-> (searchable PDF bytes, report). Raises OcrError with a readable reason. The input bytes are never modified."""
    todo = pages_needing_ocr(pdf_bytes)
    if not todo:
        raise OcrError("no scanned pages were found")
    limit = _env_int("OCR_MAX_PAGES", 40)
    if len(todo) > limit:
        raise OcrError(f"This scan has {len(todo)} pages to read; the limit is {limit} (OCR_MAX_PAGES).")
    primary, verifier, why = choose()
    if primary is None:
        raise OcrError(why)
    read = primary.read_pages(pdf_bytes, todo)
    if not any(p.lines for p in read.values()):
        raise OcrError("OCR could not read any text from the scanned pages")
    checked: dict[int, OcrPage] = {}
    note = None
    if verifier is not None:
        try:
            checked = verifier.read_pages(pdf_bytes, [p for p in todo if p in read])
        except OcrError as e:                                    # a failed second opinion must not lose the first reading
            verifier, note = None, f"verification failed: {str(e)[:120]}"
    min_agree = _env_float("OCR_AGREEMENT_MIN", 0.80)
    review_unverified = os.environ.get("OCR_REVIEW_UNVERIFIED", "1") != "0"
    pages: dict[str, dict] = {}
    for p in todo:
        if p not in read:
            continue
        info: dict = {"lines": len(read[p].lines), "coarse": read[p].coarse}
        if verifier is not None and p in checked:
            a = agreement(read[p].text, checked[p].text)
            info.update(agree=a, low=a < min_agree, num_diff=number_differences(read[p].text, checked[p].text)[:40])
        else:
            info.update(agree=None, low=review_unverified)       # nothing to compare with: treat as needing a human look
        pages[str(p)] = info
    report = {"v": 1, "engine": primary.name, "verifier": verifier.name if verifier else None, "pages": pages,
              "unread": [p for p in todo if p not in read]}
    if note:
        report["note"] = note
    return add_text_layer(pdf_bytes, read, report), report


# ------------------------------------------------------------------ flags on the extracted contract
def _fmt(pages: list[int]) -> str:
    return ", ".join(str(p) for p in sorted(pages))


def apply_flags(data, pdf_bytes: bytes) -> None:
    """For a searchable PDF made by make_searchable: say so in the warnings, and send values read from low-agreement (or unverified)
    pages to human review with the reason attached. A normal PDF is untouched."""
    from ..schema import Grounding, GroundingCheck, Milestone, DatedClause, Sourced
    rep = read_report(pdf_bytes)
    reported = {int(p) for p in (rep or {}).get("unread", [])}
    stray = [p for p in pages_needing_ocr(pdf_bytes) if p not in reported]
    if stray:
        data.warnings.append(f"Pages {_fmt(stray)} hold an image but almost no readable text. If they contain contract terms, "
                             "nothing was extracted from them (turn on OCR, or upload a text version).")
    if not rep:
        return
    pages = {int(p): v for p, v in (rep.get("pages") or {}).items()}
    low = {p for p, v in pages.items() if v.get("low")}
    num_diff = {p: set(v.get("num_diff") or []) for p, v in pages.items() if v.get("num_diff")}
    eng = rep.get("engine", "OCR")
    ver = rep.get("verifier")
    data.warnings.append(f"Pages {_fmt(list(pages))} were read from scanned images with {eng}"
                         + (f" and cross-checked with {ver}" if ver else " (no second reading to compare)") + ".")
    coarse = [p for p, v in pages.items() if v.get("coarse")]
    if coarse:
        data.warnings.append(f"On pages {_fmt(coarse)} the OCR gave no reliable line positions, so highlights there are approximate.")
    if rep.get("unread"):
        data.warnings.append(f"Pages {_fmt(rep['unread'])} could not be read by OCR; nothing was extracted from them.")
    if low:
        data.warnings.append(f"Pages {_fmt(list(low))} need a human check: " + ("the two readings disagree." if ver else "they are unverified."))
    if num_diff:
        data.warnings.append(f"The two readings differ on numbers on pages {_fmt(list(num_diff))}; values quoting those numbers need a human check.")
    items = [v for v in (getattr(data, n) for n in type(data).model_fields) if isinstance(v, Sourced)]
    items += list(data.payment_plan) + list(data.dated_clauses) + list(data.ungrounded_rows)
    for it in items:
        if not isinstance(it, (Sourced, Milestone, DatedClause)):
            continue
        if isinstance(it, Sourced) and it.value is None:
            continue
        diff = sorted(numbers(it.source_quote or "") & num_diff.get(it.source_page, set()))
        if it.source_page not in low and not diff:
            continue
        a = pages[it.source_page].get("agree") if it.source_page in pages else None
        if it.source_page in low:
            detail = (f"page {it.source_page} was read by OCR and the two readings agree only {a:.0%}" if a is not None
                      else f"page {it.source_page} was read by OCR and has not been checked against a second reading")
        else:
            detail = f"page {it.source_page}: the two OCR readings differ on a number in this quote ({', '.join(diff[:4])})"
        if it.grounding is None:
            it.grounding = Grounding(status="partial")
        it.grounding.checks.append(GroundingCheck(name="ocr_page", passed=False, detail=detail))
        it.needs_review = True
        it.confidence = min(it.confidence if it.confidence is not None else 1.0, 0.7)
