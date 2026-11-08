"""Check scanned-PDF reading on THIS machine/server configuration. Prints PASS/FAIL per step; never prints keys or page text.

    python scripts/check_ocr.py                 # uses OCR_ENGINE / QWEN_* from the environment or .env
    python scripts/check_ocr.py --pages 2       # read only the first N pages (cheaper while testing)

It turns pages of a bundled sample contract into a scanned (image-only) PDF, reads them with your configured engine(s), and reports
how many lines were found, whether the two readers agree, and whether a known phrase was recovered.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pymupdf  # noqa: E402

from app import config, ocr  # noqa: E402
from app.extract import pdf_pages  # noqa: E402

bad = 0


def step(name: str, ok: bool, detail: str = "") -> bool:
    global bad
    bad += 0 if ok else 1
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main() -> int:
    n = 3
    if "--pages" in sys.argv:
        n = max(1, int(sys.argv[sys.argv.index("--pages") + 1]))
    st = ocr.engines_status()
    for name, s in st.items():
        print(f"      {name}: {'available' if s['available'] else 'not available: ' + s['reason']}")
    primary, verifier, why = ocr.choose()
    if not step("an OCR engine is available", primary is not None, why or f"{primary.name}" + (f" + {verifier.name} to verify" if verifier else " (no second reader)")):
        return 1
    src = pymupdf.open(str(config.SAMPLES_DIR / "sample_a.pdf"))
    original = pymupdf.open()
    scan = pymupdf.open()
    for i in range(min(n, src.page_count)):
        original.insert_pdf(src, from_page=i, to_page=i)
        pg = src[i]
        sp = scan.new_page(width=pg.rect.width, height=pg.rect.height)
        sp.insert_image(sp.rect, stream=pg.get_pixmap(dpi=150, alpha=False).tobytes("jpeg", jpg_quality=70))
    truth = " ".join(pdf_pages(original.tobytes())).lower()
    data = scan.tobytes()
    step("test scan has no text layer", not any(t.strip() for t in pdf_pages(data)), f"{scan.page_count} pages")
    try:
        layered, rep = ocr.make_searchable(data)
    except ocr.OcrError as e:
        step("read the scanned pages", False, str(e)[:200])
        return 1
    step("read the scanned pages", bool(rep["pages"]), f"{len(rep['pages'])} read, {len(rep['unread'])} unread")
    got = " ".join(pdf_pages(layered)).lower()
    words = [w for w in truth.split() if len(w) > 5][:200]
    hit = sum(1 for w in words if w in got) / max(1, len(words))
    step("recovered the page's words", hit > 0.8, f"{hit:.0%} of long words")
    coarse = [p for p, v in rep["pages"].items() if v.get("coarse")]
    step("line positions are usable (highlights will be accurate)", not coarse, "approximate on pages " + ", ".join(coarse) if coarse else "")
    if rep["verifier"]:
        agree = [v["agree"] for v in rep["pages"].values() if v.get("agree") is not None]
        step("the two readers agree", bool(agree) and min(agree) >= 0.8, f"lowest page agreement {min(agree):.0%}" if agree else "")
        diffs = {p: v["num_diff"] for p, v in rep["pages"].items() if v.get("num_diff")}
        step("the two readers agree on every number", not diffs, "differ on pages " + ", ".join(diffs) if diffs else "")
    print("\nAll checks passed." if not bad else f"\n{bad} check(s) failed.")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
