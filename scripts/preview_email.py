"""Write the designed emails and image cards to docs/email-previews/ so you can open them in a browser (no sending, no server).

    python scripts/preview_email.py [--name "Your Name"] [--title "Unlimited Innovations India Pvt. Ltd"] [--out docs/email-previews]

Uses clearly synthetic sample data. Open the .html files; the card images and the logo are referenced as local files.
"""
import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import emailcards as ec  # noqa: E402

PLAN = [("Booking / Signing", "2025-03-15"), ("First Instalment", "2025-09-15"), ("Second Instalment", "2026-03-15"),
        ("Third Instalment", "2026-12-15"), ("Final Instalment", "2027-06-30")]
SAMPLES = {
    "contract_ready": {"contract": {"contract_id": "", "contract_name": "sample_a.pdf", "unit_id": "MCR-1204", "buyer": "Sample Buyer",
                                    "currency": "AED", "price": 2450000, "handover_date": "2027-06-30", "jurisdiction": "ae_dubai", "milestones": 5,
                                    "payment_plan_percent_sum": 100.0, "warnings": 0, "needs_review": 2,
                                    "plan": [{"name": n, "percent": 20, "due_date": d} for n, d in PLAN]}},
    "alert": {"alert": {"contract_id": "", "contract_name": "sample_a.pdf", "event_type": "overdue", "severity": "high",
                        "message": "Second Instalment (20%): overdue, due 2026-03-15", "due_date": "2026-03-15", "days_until": -237,
                        "label": "Second Instalment (20%)", "page": 6}},
    "review_needed": {"review": {"contract_id": "", "contract_name": "sample_a.pdf", "field": "dated_clauses.1", "status": "partial",
                                 "confidence": 0.82, "page": 5}},
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="Your Name")
    ap.add_argument("--title", default="Unlimited Innovations India Pvt. Ltd")
    ap.add_argument("--out", default="docs/email-previews")
    a = ap.parse_args()
    out = (ROOT / a.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / "assets/brand/email-logo.png", out / "logo.png")
    st = {"base": "", "secret": "", "name": a.name, "title": a.title}
    for kind, data in SAMPLES.items():
        (out / f"card_{kind}.png").write_bytes(ec.render_card(ec.card_payload(kind, data)))
        e = ec.build_email(kind, data, st, local_dir="")
        (out / f"{kind}.html").write_text(e["html"], encoding="utf-8")
        print(f"{kind}: subject = {e['subject']}")
    print("wrote", out)


if __name__ == "__main__":
    main()
