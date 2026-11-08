"""Turn a scanned PDF into a SEARCHABLE one by adding an invisible text layer at the OCR positions.

Everything downstream (quote search, grounding, the highlighted evidence boxes) already works on a PDF's text layer, so this one step
is what makes scanned contracts work end to end. The scanned image stays exactly as it was; the text is invisible (render mode 3).
The original upload is kept unchanged by the caller.
"""
from __future__ import annotations

import json

import pymupdf

from .types import OcrPage

REPORT_PREFIX = "spa-ocr:v1:"
_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", "−": "-",
                      "…": "...", " ": " ", "•": "-", "​": ""})


def clean(text: str) -> str:
    """Base-14 fonts cannot draw every character, so typographic punctuation is mapped to its plain form. Quote matching ignores
    punctuation anyway, so nothing is lost."""
    t = text.translate(_MAP)
    return "".join(ch if ord(ch) < 256 else "?" for ch in t).strip()


def add_text_layer(pdf_bytes: bytes, pages: dict[int, OcrPage], report: dict | None = None) -> bytes:
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        for pno, op in sorted(pages.items()):
            if not 1 <= pno <= doc.page_count:
                continue
            page = doc[pno - 1]
            sx = page.rect.width / op.width if op.width else 1.0
            sy = page.rect.height / op.height if op.height else 1.0
            for line in op.lines:
                text = clean(line.text)
                if not text:
                    continue
                x0, y0, x1, y1 = line.bbox[0] * sx, line.bbox[1] * sy, line.bbox[2] * sx, line.bbox[3] * sy
                w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
                natural = pymupdf.get_text_length(text, fontname="helv", fontsize=10)
                fs = 10 * w / natural if natural > 0 else h
                fs = max(3.0, min(fs, h * 1.25, 48.0))          # fit the width, but never taller than the line itself
                page.insert_text((x0, y1 - h * 0.2), text, fontsize=fs, fontname="helv", render_mode=3)
        if report is not None:
            meta = dict(doc.metadata or {})
            meta["keywords"] = REPORT_PREFIX + json.dumps(report, separators=(",", ":"))
            doc.set_metadata(meta)
        return doc.tobytes(garbage=3, deflate=True)


def read_report(pdf_bytes: bytes) -> dict | None:
    """The OCR report embedded by add_text_layer, or None for an ordinary PDF."""
    try:
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
            kw = (doc.metadata or {}).get("keywords") or ""
    except Exception:  # noqa: BLE001
        return None
    if not kw.startswith(REPORT_PREFIX):
        return None
    try:
        r = json.loads(kw[len(REPORT_PREFIX):])
    except ValueError:
        return None
    return r if isinstance(r, dict) else None
