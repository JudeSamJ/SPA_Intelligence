"""Page -> PNG for the vision model."""
from __future__ import annotations

import pymupdf


def render_page_png(pdf_bytes: bytes, page_no: int, dpi: int = 200) -> tuple[bytes, int, int, float, float]:
    """-> (png, width_px, height_px, page_width_pt, page_height_pt)."""
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        page = doc[page_no - 1]
        pix = page.get_pixmap(dpi=dpi, alpha=False)
        return pix.tobytes("png"), pix.width, pix.height, float(page.rect.width), float(page.rect.height)
