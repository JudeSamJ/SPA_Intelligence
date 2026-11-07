"""Evidence boxes: find a quote on a PDF page and return its rectangles. Pure PyMuPDF + string logic.

Strategy (deterministic):
1. Take the page's words with their boxes and normalise each to lowercase letters/digits only.
   Joining them gives one string in which whitespace, line breaks, quote marks, dashes and
   hyphenation ("agree-" + "ment") no longer matter.
2. Look for the normalised quote in that string (exact). Map the character span back to words.
3. If absent, fuzzy-align (rapidfuzz partial_ratio_alignment); accept at or above a configurable threshold.
4. Otherwise bbox is null (method "not_found"). Nothing is ever guessed.
"""
from __future__ import annotations

import re
from functools import lru_cache

import pymupdf
from rapidfuzz import fuzz

from .schema import Evidence

FUZZY_THRESHOLD = 88.0   # 0-100; overridable from rules/grounding.yaml via set_fuzzy_threshold


def set_fuzzy_threshold(v: float) -> None:
    global FUZZY_THRESHOLD
    FUZZY_THRESHOLD = float(v)


def key(s: str) -> str:
    s = (s or "").replace(" ", " ")
    return re.sub(r"[\W_]+", "", s.lower())


def _page_words(page) -> list[tuple[str, tuple[float, float, float, float], tuple[int, int]]]:
    out = []
    for x0, y0, x1, y1, w, block, line, _n in page.get_text("words"):
        k = key(w)
        if k:
            out.append((k, (x0, y0, x1, y1), (block, line)))
    return out


def _span_to_words(words, start: int, end: int):
    pos, hit = 0, []
    for k, rect, bl in words:
        a, b = pos, pos + len(k)
        if b > start and a < end:
            hit.append((rect, bl))
        pos = b
    return hit


def _line_rects(hit) -> list[list[float]]:
    lines: dict[tuple[int, int], list[float]] = {}
    for (x0, y0, x1, y1), bl in hit:
        r = lines.get(bl)
        if r is None:
            lines[bl] = [x0, y0, x1, y1]
        else:
            r[0], r[1], r[2], r[3] = min(r[0], x0), min(r[1], y0), max(r[2], x1), max(r[3], y1)
    return [[round(v, 2) for v in r] for r in lines.values()]


def locate_on_page(page, quote: str) -> tuple[list[list[float]], str]:
    qk = key(quote)
    if not qk:
        return [], "not_found"
    words = _page_words(page)
    text = "".join(w[0] for w in words)
    i = text.find(qk)
    method = "exact"
    if i < 0:
        al = fuzz.partial_ratio_alignment(qk, text)
        if al is None or al.score < FUZZY_THRESHOLD:
            return [], "not_found"
        i, method = al.dest_start, "fuzzy"
        end = al.dest_end
    else:
        end = i + len(qk)
    hit = _span_to_words(words, i, end)
    return (_line_rects(hit), method) if hit else ([], "not_found")


def _union(rects: list[list[float]]) -> list[float] | None:
    if not rects:
        return None
    return [round(min(r[0] for r in rects), 2), round(min(r[1] for r in rects), 2),
            round(max(r[2] for r in rects), 2), round(max(r[3] for r in rects), 2)]


def locate(pdf_bytes: bytes, page_no: int | None, quote: str | None) -> Evidence:
    """Evidence for (page, quote). Tries the stated page first, then every other page."""
    if not quote or not quote.strip():
        return Evidence(page=page_no, quote=quote, method="not_found")
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as doc:
        order = []
        if page_no and 1 <= page_no <= doc.page_count:
            order.append(page_no)
        order += [p for p in range(1, doc.page_count + 1) if p not in order]
        best = None
        for pn in order:
            page = doc[pn - 1]
            rects, method = locate_on_page(page, quote)
            if rects and method == "exact":
                return Evidence(page=pn, quote=quote, bbox=_union(rects), rects=rects,
                                page_width=page.rect.width, page_height=page.rect.height, method="exact")
            if rects and best is None:
                best = Evidence(page=pn, quote=quote, bbox=_union(rects), rects=rects,
                                page_width=page.rect.width, page_height=page.rect.height, method=method)
        if best:
            return best
        pn = page_no if page_no and 1 <= page_no <= doc.page_count else None
        pg = doc[pn - 1] if pn else None
        return Evidence(page=pn, quote=quote, method="not_found",
                        page_width=pg.rect.width if pg else None, page_height=pg.rect.height if pg else None)


@lru_cache(maxsize=64)
def _render_cached(pdf_hash: str, pdf_bytes_len: int, page_no: int, scale: float, _b: bytes) -> bytes:
    with pymupdf.open(stream=_b, filetype="pdf") as doc:
        pix = doc[page_no - 1].get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
        return pix.tobytes("png")


def render_page_png(pdf_bytes: bytes, page_no: int, scale: float = 1.5) -> bytes:
    import hashlib
    h = hashlib.sha256(pdf_bytes).hexdigest()
    return _render_cached(h, len(pdf_bytes), page_no, round(scale, 2), pdf_bytes)
