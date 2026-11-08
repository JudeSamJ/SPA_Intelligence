"""Docling adapter against Docling's REAL geometry classes. Skipped when Docling is not installed (it is optional and heavy).

What this proves: our conversion of Docling's OCR cells (bottom-left or top-left origin) into PDF points is right, using Docling's own
classes. What it does NOT prove: a full OCR run, which needs Docling's models downloaded (not possible in every environment)."""
import pytest

pytest.importorskip("docling_core")
from types import SimpleNamespace  # noqa: E402

from docling_core.types.doc import CoordOrigin  # noqa: E402
from docling_core.types.doc.page import BoundingRectangle, ColorRGBA, TextCell  # noqa: E402

from app.ocr.docling_engine import DoclingOcr, _cell_box, _pages_from_result  # noqa: E402


def cell(text, l, t, r, b, origin):
    rect = BoundingRectangle(r_x0=l, r_y0=t, r_x1=r, r_y1=t, r_x2=r, r_y2=b, r_x3=l, r_y3=b, coord_origin=origin)
    return TextCell(index=0, rgba=ColorRGBA(r=0, g=0, b=0, a=255), rect=rect, text=text, orig=text, from_ocr=True)


def test_top_left_cells_are_used_as_they_are():
    assert _cell_box(cell("x", 100, 200, 300, 240, CoordOrigin.TOPLEFT), 842.0) == (100.0, 200.0, 300.0, 240.0)


def test_bottom_left_cells_are_flipped_to_top_left():
    # a cell 600..640 up from the bottom of an 842-point page sits 202..242 down from the top
    assert _cell_box(cell("x", 100, 640, 300, 600, CoordOrigin.BOTTOMLEFT), 842.0) == (100.0, 202.0, 300.0, 242.0)


def test_pages_are_mapped_back_to_their_original_numbers_and_empty_cells_dropped():
    res = SimpleNamespace(pages=[
        SimpleNamespace(cells=[cell("Handover Date", 50, 100, 400, 120, CoordOrigin.TOPLEFT), cell("  ", 1, 1, 9, 9, CoordOrigin.TOPLEFT)]),
        SimpleNamespace(cells=[cell("Grace Period", 60, 300, 300, 320, CoordOrigin.TOPLEFT)])])
    out = _pages_from_result(res, [3, 5], [(595.0, 842.0), (595.0, 842.0)])        # Docling saw only original pages 3 and 5
    assert sorted(out) == [3, 5] and out[3].lines[0].text == "Handover Date" and len(out[3].lines) == 1
    assert out[5].lines[0].bbox == (60.0, 300.0, 300.0, 320.0) and out[5].engine == "docling"


def test_the_engine_reports_itself_available_when_installed():
    assert DoclingOcr().available() == (True, "")
