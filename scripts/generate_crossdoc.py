"""Generate 3 synthetic multi-document sets (SPA + brochure + regulator filing + CRM export) with PLANTED mismatches.

Writes samples/crossdoc/<set_id>/{spa.pdf(copy), brochure.pdf, filing.pdf, crm.csv, manifest.json, facts.json}.
`manifest.json` lists the planted conflicts (used to measure precision/recall). `facts.json` holds, per PDF, the
facts and verbatim quotes the document states: this is the TEST ORACLE that stands in for the LLM in tests/demo.
Run:  python scripts/generate_crossdoc.py
"""
from __future__ import annotations

import csv
import json
import shutil
from datetime import date
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples" / "crossdoc"

SETS = {
    "set_1": {
        "spa": "sample_d_rera.pdf", "currency": "INR", "project": "Kalyani Heights", "unit_display": "Unit KH-T2-1503",
        "brochure": {"price": 8250000, "area_sqft": 865.0, "handover": "2026-12-31", "plan": [10, 20, 20, 20, 20, 10],
                     "delay_rate": 60.0, "reg": "P99999000001"},
        "filing": {"reg": "P99999000001", "handover": "2027-06-30"},
        "crm": {"unit": "KH T2 1503", "price": 8450000, "area": 865.0, "handover": "31-12-2026", "plan": "10/20/20/20/20/10",
                "rate": 60.0, "reg": "P99999000001"},
        "planted": [{"attribute": "price", "docs": ["brochure", "spa"]},
                    {"attribute": "handover_date", "docs": ["filing", "spa"]}],
    },
    "set_2": {
        "spa": "sample_a.pdf", "currency": "AED", "project": "Marina Crest Residences", "unit_display": "Unit MCR-1204",
        "brochure": {"price": 2450000, "area_sqft": 1180.0, "handover": "2027-06-30", "plan": [10, 20, 20, 20, 30],
                     "delay_rate": 6.0, "reg": "DLD-8841"},
        "filing": {"reg": "DLD-8814", "handover": "2027-06-30"},
        "crm": {"unit": "mcr-1204", "price": 2450000, "area": 1150.0, "handover": "30-06-2027", "plan": "20/20/20/20/20",
                "rate": 6.0, "reg": "DLD-8841"},
        "planted": [{"attribute": "payment_plan", "docs": ["brochure", "spa"]},
                    {"attribute": "area_sqft", "docs": ["crm", "spa"]},
                    {"attribute": "registration_number", "docs": ["filing", "brochure"]}],
    },
    "set_3": {
        "spa": "sample_b.pdf", "currency": "AED", "project": "Palm Horizon Towers", "unit_display": "Unit PHT-B-0807",
        "brochure": {"price": 1875000, "area_sqft": 1025.5, "handover": "2028-03-31", "plan": [10, 10, 10, 15, 15, 10, 30],
                     "delay_rate": 10.0, "reg": "DLD-5520"},
        "filing": {"reg": "DLD-5520", "handover": "2028-03-31"},
        "crm": {"unit": "PHT-B-0807", "price": 1875000, "area": 95.27, "handover": "31-03-2028",
                "plan": "10/10/10/15/15/10/30", "rate": 7.0, "reg": "DLD-5520", "area_unit": "sqm"},
        "planted": [{"attribute": "delay_rate", "docs": ["brochure", "spa"]}],
    },
}


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def build_pdf(path: Path, title: str, lines: list[str]) -> None:
    st = getSampleStyleSheet()
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm, topMargin=22 * mm,
                            bottomMargin=22 * mm, title=title, author="Synthetic sample", invariant=1)
    story = [Paragraph(title, st["Title"]), Paragraph("Synthetic sample document for cross-document checks.", st["Italic"]),
             Spacer(1, 10)]
    for ln in lines:
        story += [Paragraph(ln, st["BodyText"]), Spacer(1, 4)]
    doc.build(story)


def main() -> None:
    truth = json.loads((ROOT / "ground_truth.json").read_text())
    for sid, s in SETS.items():
        d = OUT / sid
        d.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / "samples" / s["spa"], d / "spa.pdf")
        cur, b, f, c = s["currency"], s["brochure"], s["filing"], s["crm"]
        plan_txt = " / ".join(f"{p:g}%" for p in b["plan"])
        blines = {
            "unit_id": s["unit_display"],
            "area_sqft": f"Saleable area: {b['area_sqft']:,.2f} sq ft",
            "price": f"Price: {cur} {b['price']:,}",
            "handover_date": f"Possession: {long_date(b['handover'])}",
            "payment_plan": f"Payment plan: {plan_txt}",
            "delay_rate": f"Delay compensation: {cur} {b['delay_rate']:.2f} per square foot per year" if s["spa"] == "sample_b.pdf"
                          else f"Delay compensation: {b['delay_rate']:g}% per annum" if cur == "AED" else
                          f"Delay compensation: {cur} {b['delay_rate']:.2f} per square foot per year",
            "registration_number": f"Registration number: {b['reg']}",
        }
        build_pdf(d / "brochure.pdf", f"{s['project']} - Brochure", [blines[k] for k in blines])
        flines = {"unit_id": s["unit_display"], "registration_number": f"Registration number: {f['reg']}",
                  "handover_date": f"Proposed date of completion: {long_date(f['handover'])}"}
        build_pdf(d / "filing.pdf", f"{s['project']} - Regulator project filing", [flines[k] for k in flines])
        with open(d / "crm.csv", "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["Unit No", "Customer", "Agreed Price", "Area", "Possession Date", "Plan %", "Delay Rate", "RERA No"])
            w.writerow([c["unit"], "CRM Customer", c["price"], c["area"], c["handover"], c["plan"], c["rate"], c["reg"]])
        facts = {"brochure": {"doc": "brochure.pdf", "quotes": blines, "values": {
                     "unit_id": s["unit_display"].split(" ", 1)[1], "area_sqft": b["area_sqft"], "price": float(b["price"]),
                     "handover_date": b["handover"], "payment_plan": b["plan"], "delay_rate": b["delay_rate"],
                     "registration_number": b["reg"]}},
                 "filing": {"doc": "filing.pdf", "quotes": flines, "values": {
                     "unit_id": s["unit_display"].split(" ", 1)[1], "registration_number": f["reg"], "handover_date": f["handover"]}}}
        manifest = {"set_id": sid, "unit_key": s["unit_display"].split(" ", 1)[1], "spa": "spa.pdf", "currency": cur,
                    "documents": [{"type": "spa", "file": "spa.pdf"}, {"type": "brochure", "file": "brochure.pdf"},
                                  {"type": "regulator_filing", "file": "filing.pdf"}, {"type": "crm_export", "file": "crm.csv"}],
                    "crm_area_unit": c.get("area_unit", "sqft"), "planted": s["planted"],
                    "note": "SYNTHETIC. 'planted' lists the mismatches placed on purpose."}
        (d / "manifest.json").write_text(json.dumps(manifest, indent=2))
        (d / "facts.json").write_text(json.dumps(facts, indent=2))
        print("wrote", d.relative_to(ROOT))


if __name__ == "__main__":
    main()
