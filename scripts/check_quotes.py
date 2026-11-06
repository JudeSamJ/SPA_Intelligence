"""Free diagnostic (no LLM call): for a cached extraction, show whether each quote is in the PDF and,
if not, exactly where the quote stops matching.   python scripts/check_quotes.py samples/sample_a.pdf"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: E402
from app.extract import load_cached, locate_quote, pdf_pages, quote_key  # noqa: E402

path = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "samples" / "sample_a.pdf")
data = path.read_bytes()
c = load_cached(data)
if not c:
    sys.exit(f"No cached extraction for {path.name} with {config.model_tag()} (nothing to check; no API call made).")
pages = pdf_pages(data)
keys = [quote_key(p) for p in pages]
items = [(n, getattr(c, n)) for n in ("buyer", "unit_id", "price", "area_sqft", "handover_date", "grace_period_days",
                                       "delay_rate", "delay_basis", "delay_cap", "cancellation_clause")]
items += [(f"payment_plan[{i}]", m) for i, m in enumerate(c.payment_plan, 1)]
for name, it in items:
    q = it.source_quote
    if not q:
        continue
    ok = locate_quote(pages, q, it.source_page)
    print(f"{'OK ' if ok else 'BAD'} {name}  (claimed page {it.source_page}, found page {ok})")
    if not ok:
        k = quote_key(q)
        best = max(range(len(k) + 1), key=lambda n: (k[:n] in "".join(keys), n)) if k else 0
        n = max(n for n in range(len(k) + 1) if k[:n] in "".join(keys))
        print("   QUOTE :", repr(q))
        print(f"   matches the PDF for its first {n} of {len(k)} letters/digits; diverges at: {k[n:n+40]!r}")
        i = "".join(keys).find(k[:n]) if n else -1
        if i >= 0:
            print("   PDF has:", repr("".join(keys)[i + n:i + n + 40]))
print("\nWarnings stored in cache:", c.warnings)
