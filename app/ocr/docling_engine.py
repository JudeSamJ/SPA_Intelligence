"""Docling as an OCR engine. Optional and heavy (installs PyTorch and downloads models): pip install docling

Docling runs its own page layout and OCR pipeline. We use its line-level OCR cells (text plus position) for each page. If Docling is
not installed the engine reports why and is never simulated.
"""
from __future__ import annotations

import importlib.util
import tempfile
from pathlib import Path

import pymupdf

from .types import OcrEngine, OcrError, OcrLine, OcrPage


class DoclingOcr(OcrEngine):
    name = "docling"

    def available(self) -> tuple[bool, str]:
        if importlib.util.find_spec("docling") is None:
            return False, "not installed (pip install docling; needs several GB and is too large for a 512 MB host)"
        return True, ""

    def read_pages(self, pdf_bytes: bytes, pages: list[int]) -> dict[int, OcrPage]:
        try:
            from docling.datamodel.base_models import InputFormat                     # type: ignore
            from docling.datamodel.pipeline_options import PdfPipelineOptions         # type: ignore
            from docling.document_converter import DocumentConverter, PdfFormatOption  # type: ignore
        except ImportError as e:
            raise OcrError("Docling is not installed") from e
        # Docling gets a copy holding only the pages that need OCR, in order; results are mapped back to the original numbers.
        with pymupdf.open(stream=pdf_bytes, filetype="pdf") as src:
            sub = pymupdf.open()
            for p in pages:
                sub.insert_pdf(src, from_page=p - 1, to_page=p - 1)
            sizes = [(float(pg.rect.width), float(pg.rect.height)) for pg in sub]
            data = sub.tobytes()
            sub.close()
        opts = PdfPipelineOptions()
        opts.do_ocr = True
        opts.do_table_structure = False                 # we want plain text lines; tables are read line by line like everything else
        try:                                              # these pages are images: OCR the whole page
            from docling.datamodel.pipeline_options import OcrMode     # type: ignore
            opts.ocr_options.mode = OcrMode.FULL_PAGE
        except (ImportError, AttributeError):
            try:
                opts.ocr_options.force_full_page_ocr = True            # older Docling releases
            except AttributeError:
                pass
        conv = DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)})
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "scan.pdf"
            f.write_bytes(data)
            try:
                res = conv.convert(str(f))
            except Exception as e:  # noqa: BLE001
                raise OcrError(f"Docling could not read the pages ({type(e).__name__})") from None
        return _pages_from_result(res, pages, sizes)


def _pages_from_result(res, pages: list[int], sizes: list[tuple[float, float]]) -> dict[int, OcrPage]:
    """Docling result -> {original page number: OcrPage}. Prefers the OCR line cells; falls back to the document's text items."""
    out: dict[int, OcrPage] = {}
    result_pages = list(getattr(res, "pages", []) or [])
    for idx, p in enumerate(pages):
        w, h = sizes[idx]
        op = OcrPage(page=p, width=w, height=h, engine="docling")
        rp = result_pages[idx] if idx < len(result_pages) else None
        for cell in (getattr(rp, "cells", None) or []):
            text = (getattr(cell, "text", "") or "").strip()
            box = _cell_box(cell, h)
            if text and box:
                op.lines.append(OcrLine(text, box))
        if op.lines:
            out[p] = op
    if out:
        return out
    doc = getattr(res, "document", None)                    # fallback: the structured document's text items with provenance
    for item in (getattr(doc, "texts", None) or []):
        text = (getattr(item, "text", "") or "").strip()
        for prov in (getattr(item, "prov", None) or []):
            n = int(getattr(prov, "page_no", 0) or 0)
            if not (1 <= n <= len(pages)) or not text:
                continue
            w, h = sizes[n - 1]
            b = prov.bbox
            try:
                tl = b.to_top_left_origin(h)
                box = (float(tl.l), float(tl.t), float(tl.r), float(tl.b))
            except Exception:  # noqa: BLE001
                continue
            op = out.setdefault(pages[n - 1], OcrPage(page=pages[n - 1], width=w, height=h, engine="docling"))
            op.lines.append(OcrLine(text, box))
    return out


def _cell_box(cell, page_h: float):
    """A Docling text cell's rectangle as (x0, y0, x1, y1), top-left origin, in points."""
    try:
        bb = cell.rect.to_bounding_box()
        try:
            bb = bb.to_top_left_origin(page_h)
        except Exception:  # noqa: BLE001
            pass
        x0, x1 = sorted((float(bb.l), float(bb.r)))
        y0, y1 = sorted((float(bb.t), float(bb.b)))
        return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None
    except Exception:  # noqa: BLE001
        return None
