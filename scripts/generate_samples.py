"""Generate 3 synthetic English SPA PDFs plus ground_truth.json from one dict of truth values.

Run:  python scripts/generate_samples.py
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

# ---------------------------------------------------------------------------
# TRUTH VALUES: single source for the PDFs and ground_truth.json
# delay_cap is expressed as a percentage of the purchase price (None = no cap).
# ---------------------------------------------------------------------------
TRUTH = {
    "sample_a": {
        "file": "sample_a.pdf",
        "project": "Marina Crest Residences",
        "developer": "Crestline Developments LLC",
        "buyer": "Layla Hassan Al Mansoori",
        "unit_id": "MCR-1204",
        "floor": "12th",
        "price": 2450000,
        "area_sqft": 1180.0,
        "spa_date": "2025-03-15",
        "handover_date": "2027-06-30",
        "grace_period_days": 60,
        "delay_rate": 6.0,
        "delay_basis": "percent_per_annum",
        "delay_cap": 10.0,
        "has_cancellation_clause": True,
        "payment_plan": [
            {"name": "Booking / Signing", "percent": 20.0, "due_date": "2025-03-15", "trigger": "On signing of this Agreement"},
            {"name": "First Instalment", "percent": 20.0, "due_date": "2025-09-15", "trigger": "Six months after signing"},
            {"name": "Second Instalment", "percent": 20.0, "due_date": "2026-03-15", "trigger": "Twelve months after signing"},
            {"name": "Third Instalment", "percent": 20.0, "due_date": "2026-12-15", "trigger": "Upon completion of the structural works"},
            {"name": "Final Instalment", "percent": 20.0, "due_date": "2027-06-30", "trigger": "Upon notice of completion and handover"},
        ],
    },
    "sample_b": {
        "file": "sample_b.pdf",
        "project": "Palm Horizon Towers",
        "developer": "Horizon Gulf Properties PJSC",
        "buyer": "Rajesh Kumar Menon",
        "unit_id": "PHT-B-0807",
        "floor": "8th",
        "price": 1875000,
        "area_sqft": 1025.5,
        "spa_date": "2025-08-01",
        "handover_date": "2028-03-31",
        "grace_period_days": 90,
        "delay_rate": 7.0,  # AED per sq ft per year
        "delay_basis": "fixed_per_sqft_per_year",
        "delay_cap": None,
        "has_cancellation_clause": True,
        "payment_plan": [
            {"name": "Booking Deposit", "percent": 10.0, "due_date": "2025-08-01", "trigger": "On signing of this Agreement"},
            {"name": "Second Payment", "percent": 10.0, "due_date": "2025-11-01", "trigger": "Within 90 days of signing"},
            {"name": "Excavation Milestone", "percent": 10.0, "due_date": "2026-02-01", "trigger": "On commencement of excavation works"},
            {"name": "Foundation Milestone", "percent": 15.0, "due_date": "2026-06-01", "trigger": "On completion of foundation and basement slab"},
            {"name": "Podium Milestone", "percent": 15.0, "due_date": "2026-12-01", "trigger": "On completion of podium slab"},
            {"name": "Structure Milestone", "percent": 10.0, "due_date": "2027-08-01", "trigger": "On completion of structural frame to roof level"},
            {"name": "Handover Payment", "percent": 30.0, "due_date": "2028-03-31", "trigger": "On notice of completion and handover of the Unit"},
        ],
    },
    "sample_c": {
        "file": "sample_c.pdf",
        "project": "Desert Bloom Villas",
        "developer": "Sandstone Estates FZ-LLC",
        "buyer": "Fatima Zahra Bin Rashid",
        "unit_id": "DBV-VILLA-37",
        "floor": "ground and first",
        "price": 3980000,
        "area_sqft": 3120.0,
        "spa_date": "2025-11-10",
        "handover_date": "2027-12-31",
        "grace_period_days": 30,
        "delay_rate": 4.5,
        "delay_basis": "percent_per_annum",
        "delay_cap": 5.0,
        "has_cancellation_clause": False,
        # Deliberate error: percentages sum to 95, not 100.
        "payment_plan": [
            {"name": "Booking Deposit", "percent": 20.0, "due_date": "2025-11-10", "trigger": "On signing of this Agreement"},
            {"name": "First Instalment", "percent": 15.0, "due_date": "2026-03-10", "trigger": "On completion of site clearance and piling"},
            {"name": "Second Instalment", "percent": 15.0, "due_date": "2026-08-10", "trigger": "On completion of ground floor slab"},
            {"name": "Third Instalment", "percent": 15.0, "due_date": "2027-01-10", "trigger": "On completion of first floor slab"},
            {"name": "Fourth Instalment", "percent": 15.0, "due_date": "2027-07-10", "trigger": "On completion of external walls and roofing"},
            {"name": "Handover Payment", "percent": 15.0, "due_date": "2027-12-31", "trigger": "On notice of completion and handover of the Villa"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def aed(n: float) -> str:
    return f"AED {n:,.0f}" if float(n).is_integer() else f"AED {n:,.2f}"


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def pct(p: float) -> str:
    return f"{p:g}%"


NUM_WORDS = {1: "one", 2: "two", 3: "three", 4: "four", 5: "five", 6: "six", 7: "seven"}


def build_styles():
    ss = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=ss["Title"], fontName="Times-Bold", fontSize=17, spaceAfter=6),
        "sub": ParagraphStyle("s", parent=ss["Normal"], fontName="Times-Roman", fontSize=11, alignment=1, spaceAfter=4),
        "h": ParagraphStyle("h", parent=ss["Heading2"], fontName="Times-Bold", fontSize=12, spaceBefore=12, spaceAfter=5),
        "p": ParagraphStyle("p", parent=ss["Normal"], fontName="Times-Roman", fontSize=10.5, leading=14.5,
                            alignment=4, spaceAfter=6),
    }


# ---------------------------------------------------------------------------
# Contract text
# ---------------------------------------------------------------------------
def clauses(t: dict) -> list[tuple[str, list[str]]]:
    """Return [(heading, [paragraphs])] with page-break markers ('PAGEBREAK')."""
    unit = "Villa" if t["unit_id"].startswith("DBV") else "Unit"
    price = aed(t["price"])
    grace = t["grace_period_days"]
    hd = long_date(t["handover_date"])

    if t["delay_basis"] == "percent_per_annum":
        delay_text = (
            f"If the Seller fails to complete construction of the {unit} and to serve the Notice of Completion on or before "
            f"the Handover Date, as extended by the Grace Period of {grace} days, the Seller shall pay to the Buyer, as "
            f"liquidated damages and not as a penalty, interest at the rate of {t['delay_rate']:g}% per annum on the Purchase "
            f"Price, calculated pro rata for each day of delay occurring after the expiry of the Grace Period until the "
            f"date on which the Notice of Completion is served."
        )
    else:
        delay_text = (
            f"If the Seller fails to complete construction of the {unit} and to serve the Notice of Completion on or before "
            f"the Handover Date, as extended by the Grace Period of {grace} days, the Seller shall pay to the Buyer, as "
            f"liquidated damages and not as a penalty, compensation at the fixed rate of AED {t['delay_rate']:.2f} per square foot "
            f"of the Saleable Area per annum, calculated pro rata for each day of delay occurring after the expiry of the "
            f"Grace Period until the date on which the Notice of Completion is served."
        )
    if t["delay_cap"] is not None:
        cap_text = (
            f"The aggregate amount payable by the Seller under this Clause 5.3 shall not exceed {t['delay_cap']:g}% of the "
            f"Purchase Price."
        )
    else:
        cap_text = (
            "The compensation payable under this Clause 5.3 is not subject to any cap or maximum limit and shall continue "
            "to accrue until the Notice of Completion is served."
        )

    n = len(t["payment_plan"])
    out: list[tuple[str, list[str]]] = []

    out.append(("1. DEFINITIONS AND INTERPRETATION", [
        f"1.1 In this Agreement the following expressions have the meanings set opposite them: <b>\"Agreement\"</b> means this "
        f"Sale and Purchase Agreement together with its Schedules; <b>\"Project\"</b> means the development known as "
        f"{t['project']} situated in the Emirate of Dubai, United Arab Emirates; <b>\"{unit}\"</b> means the property "
        f"identified in Schedule 1; <b>\"Purchase Price\"</b> has the meaning given in Clause 2.2; <b>\"Handover Date\"</b> "
        f"has the meaning given in Clause 5.1; <b>\"Grace Period\"</b> has the meaning given in Clause 5.2; and "
        f"<b>\"Notice of Completion\"</b> means written notice from the Seller to the Buyer that the {unit} is ready for "
        f"handover.",
        "1.2 Headings are for convenience only and do not affect interpretation. References to Clauses and Schedules are to "
        "clauses of and schedules to this Agreement. The singular includes the plural and vice versa.",
        "1.3 This Agreement shall be interpreted in accordance with the laws of the Emirate of Dubai and the federal laws of "
        "the United Arab Emirates applicable therein, including the laws regulating the registration of off-plan sales and "
        "the operation of escrow accounts for real estate developments.",
    ]))
    out.append(("2. SALE AND PURCHASE", [
        f"2.1 The Seller, {t['developer']}, agrees to sell and the Buyer, {t['buyer']}, agrees to purchase, free from all "
        f"encumbrances, the {unit} identified as <b>{t['unit_id']}</b> located on the {t['floor']} level of the Project, "
        f"together with the right to use the common areas of the Project in common with other owners, on the terms of this "
        f"Agreement.",
        f"2.2 The total price payable by the Buyer for the {unit} is <b>{price}</b> (the \"Purchase Price\"). The Purchase "
        f"Price is inclusive of the cost of the {unit} but is exclusive of registration fees, administrative fees, "
        f"service charges and any applicable taxes, all of which are payable by the Buyer in addition.",
        f"2.3 The Saleable Area of the {unit} is <b>{t['area_sqft']:,.2f} square feet</b>, as measured to the external face of "
        f"external walls and the centre line of party walls. The Saleable Area is stated for the purposes of this Agreement "
        f"and a variation of up to two per cent (2%) either way shall not entitle either party to an adjustment of the "
        f"Purchase Price.",
    ]))
    out.append(("3. PAYMENT OF THE PURCHASE PRICE", [
        f"3.1 The Buyer shall pay the Purchase Price to the Seller in {NUM_WORDS[n]} instalments in the amounts, on the "
        f"dates and upon the occurrence of the events set out in the Payment Plan in Schedule 2. Each instalment is "
        f"expressed as a percentage of the Purchase Price.",
        "3.2 All payments shall be made in United Arab Emirates Dirhams by bank transfer, manager's cheque or other cleared "
        "funds to the escrow account designated for the Project and notified to the Buyer in writing. Payment into any other "
        "account shall not discharge the Buyer's obligation.",
        "3.3 The Seller shall issue a written receipt for each instalment received within fourteen (14) days of receipt. The "
        "Buyer shall promptly notify the Seller of any discrepancy in a receipt.",
        "3.4 Time for payment of each instalment is of the essence. The Seller shall provide the Buyer with a written "
        "reminder not less than fourteen (14) days before the due date of each instalment that is linked to a stage of "
        "construction, and the Buyer acknowledges that the due date of such instalment is the date stated in Schedule 2 "
        "or, if later, seven (7) days after the Seller's written notice that the relevant stage has been achieved.",
    ]))
    out.append(("PAGEBREAK", []))
    out.append(("4. CONSTRUCTION AND SPECIFICATIONS", [
        f"4.1 The Seller shall construct the {unit} and the Project in a good and workmanlike manner, in accordance with the "
        f"plans and specifications approved by the competent authorities and in compliance with applicable building "
        f"regulations. The Seller may make minor variations to the plans and specifications where required by the "
        f"competent authorities or where necessary for technical reasons, provided such variations do not materially "
        f"reduce the Saleable Area or the quality of finishes.",
        "4.2 The Seller shall appoint a licensed consultant to supervise construction and shall procure that the "
        "construction works are inspected at each stage required by the competent authorities. The Buyer shall have no "
        "right to enter the construction site except with the prior written consent of the Seller and accompanied by a "
        "representative of the Seller.",
        "4.3 The Seller shall maintain throughout the construction period such insurance as is required by applicable law, "
        "including contractor's all-risks insurance and ten-year latent defects insurance covering structural elements.",
        "4.4 Any material change to the Project master plan that adversely affects the Buyer's access, view or use of the "
        f"{unit} shall require notice to the Buyer and, where required by law, approval of the competent authority.",
    ]))
    out.append(("5. COMPLETION AND HANDOVER", [
        f"5.1 The Seller shall complete construction of the {unit} and serve the Notice of Completion on or before "
        f"<b>{hd}</b> (the \"Handover Date\").",
        f"5.2 The Seller shall be entitled to a grace period of <b>{grace} days</b> after the Handover Date within which to "
        f"serve the Notice of Completion without liability under Clause 5.3 (the \"Grace Period\"). The Grace Period is "
        f"granted solely to accommodate delays arising from ordinary construction contingencies and does not extend the "
        f"Handover Date for any other purpose.",
        f"5.3 <b>Delay compensation.</b> {delay_text}",
        f"5.4 {cap_text}",
        f"5.5 The Handover Date shall be extended day for day for any period of delay caused by an event of force majeure "
        f"(including acts of God, war, epidemic, governmental action or restriction, and general shortage of materials not "
        f"attributable to the Seller), provided the Seller notifies the Buyer in writing within thirty (30) days of the "
        f"commencement of the event. The compensation in Clause 5.3 shall not accrue in respect of a period of force "
        f"majeure so notified.",
        f"5.6 Within fourteen (14) days after the Notice of Completion the Buyer shall inspect the {unit} together with a "
        f"representative of the Seller and shall list any snagging items. The Seller shall rectify the listed items within "
        f"a reasonable period. Possession shall be given against payment of all sums due under Schedule 2 and the "
        f"registration and administrative fees referred to in Clause 2.2.",
    ]))
    out.append(("PAGEBREAK", []))
    out.append(("6. TITLE, REGISTRATION AND SERVICE CHARGES", [
        f"6.1 The Seller warrants that it holds good and marketable title to the land on which the Project is being "
        f"developed, that the Project is registered with the competent real estate regulatory authority, and that the "
        f"sale of the {unit} has been registered in the interim register of off-plan sales.",
        f"6.2 Upon payment of the full Purchase Price and all other sums due, the Seller shall cooperate with the Buyer to "
        f"transfer title to the {unit} into the Buyer's name at the Land Department. The Buyer shall bear the transfer "
        f"and registration fees payable to the Land Department.",
        f"6.3 From the date of the Notice of Completion the Buyer shall be liable for service charges, utilities and "
        f"owners' association contributions attributable to the {unit}, at the rates determined from time to time by "
        f"the competent authority or the owners' association.",
        "6.4 The Seller shall hold the Buyer's payments in the escrow account until released against construction progress "
        "in accordance with applicable law. The Seller shall not use the escrow monies for any purpose unconnected with "
        "the Project.",
    ]))
    out.append(("7. DEFECTS LIABILITY", [
        f"7.1 The Seller shall rectify, at its own cost, any defect in workmanship or materials in the {unit} notified by "
        f"the Buyer in writing within twelve (12) months after the date of the Notice of Completion (the \"Defects "
        f"Liability Period\"), except where the defect results from fair wear and tear, misuse or alteration by the Buyer.",
        "7.2 The Seller shall be responsible for structural defects in the Project for the period prescribed by the "
        "applicable law, being not less than ten (10) years from the date of completion.",
    ]))

    if t["has_cancellation_clause"]:
        out.append(("8. TERMINATION AND CANCELLATION", [
            f"8.1 <b>Buyer's right to cancel for delay.</b> If the Seller has not served the Notice of Completion within "
            f"one hundred and eighty (180) days after the expiry of the Grace Period, the Buyer may, by written notice to "
            f"the Seller, cancel this Agreement, whereupon the Seller shall refund to the Buyer all sums paid under this "
            f"Agreement (without interest) within sixty (60) days of the date of the Buyer's notice.",
            "8.2 <b>Seller's right to terminate.</b> If the Buyer fails to pay any instalment within thirty (30) days "
            "after written notice of non-payment, the Seller may terminate this Agreement by written notice, in which case "
            "the Seller may retain such amount as is permitted under applicable law and shall refund the balance, if any, "
            "to the Buyer.",
            "8.3 Termination of this Agreement shall not affect any accrued rights or liabilities of either party at the "
            "date of termination.",
        ]))
        next_no = 9
    else:
        next_no = 8

    out.append((f"{next_no}. ASSIGNMENT", [
        f"{next_no}.1 The Buyer may not assign or transfer the benefit of this Agreement before the payment of the "
        f"instalments due up to the date of assignment and without the prior written consent of the Seller, which shall "
        f"not be unreasonably withheld. An administrative fee shall be payable to the Seller in connection with any "
        f"approved assignment.",
        f"{next_no}.2 The Seller may assign its rights and obligations under this Agreement to an affiliate or successor "
        f"developer approved by the competent authority, provided the assignee assumes all obligations of the Seller "
        f"hereunder.",
    ]))
    out.append((f"{next_no + 1}. NOTICES", [
        f"{next_no + 1}.1 Any notice under this Agreement shall be in writing and delivered by hand, by registered "
        f"courier or by email to the address of the recipient set out in Schedule 1. A notice delivered by hand is "
        f"deemed received on delivery; a notice sent by courier on the third business day after dispatch; and a "
        f"notice sent by email on the next business day after sending.",
    ]))
    out.append((f"{next_no + 2}. CONFIDENTIALITY, ENTIRE AGREEMENT AND GOVERNING LAW", [
        f"{next_no + 2}.1 Each party shall keep the terms of this Agreement confidential except as required by law, "
        f"by a competent authority, or for the purpose of obtaining professional advice or financing.",
        f"{next_no + 2}.2 This Agreement, together with its Schedules, constitutes the entire agreement between the "
        f"parties relating to its subject matter and supersedes all prior negotiations, brochures and representations. "
        f"Any amendment must be in writing and signed by both parties.",
        f"{next_no + 2}.3 This Agreement is governed by the laws of the Emirate of Dubai and the federal laws of the "
        f"United Arab Emirates. The courts of Dubai shall have exclusive jurisdiction, without prejudice to the "
        f"jurisdiction of the specialised real estate dispute resolution centre where applicable.",
    ]))
    return out


def story_for(t: dict, st: dict) -> list:
    unit = "Villa" if t["unit_id"].startswith("DBV") else "Unit"
    s: list = []
    s.append(Paragraph("SALE AND PURCHASE AGREEMENT", st["title"]))
    s.append(Paragraph(f"{t['project']}, Dubai, United Arab Emirates", st["sub"]))
    s.append(Paragraph(f"Dated {long_date(t['spa_date'])}", st["sub"]))
    s.append(Spacer(1, 8))
    s.append(Paragraph("PARTIES", st["h"]))
    s.append(Paragraph(
        f"(1) <b>{t['developer']}</b>, a company duly incorporated and existing under the laws of the United Arab "
        f"Emirates (the \"Seller\"); and", st["p"]))
    s.append(Paragraph(
        f"(2) <b>{t['buyer']}</b>, the individual identified in Schedule 1 (the \"Buyer\").", st["p"]))
    s.append(Paragraph("BACKGROUND", st["h"]))
    s.append(Paragraph(
        f"(A) The Seller is developing the Project known as {t['project']}. (B) The Seller has agreed to sell and the "
        f"Buyer has agreed to buy the {unit} described below on the terms and conditions of this Agreement.", st["p"]))

    for heading, paras in clauses(t):
        if heading == "PAGEBREAK":
            s.append(PageBreak())
            continue
        s.append(Paragraph(heading, st["h"]))
        for p in paras:
            s.append(Paragraph(p, st["p"]))

    # Schedule 1 on its own page
    s.append(PageBreak())
    s.append(Paragraph("SCHEDULE 1: UNIT DETAILS", st["h"]))
    rows = [
        ["Item", "Details"],
        ["Project", t["project"]],
        ["Seller", t["developer"]],
        ["Buyer", t["buyer"]],
        [f"{unit} number", t["unit_id"]],
        ["Level", t["floor"]],
        ["Saleable Area", f"{t['area_sqft']:,.2f} sq ft"],
        ["Purchase Price", aed(t["price"])],
        ["Notices to Seller", "Sales Administration, Project Sales Office, Dubai, UAE"],
        ["Notices to Buyer", "As set out in the Buyer's registration form"],
    ]
    s.append(table(rows, [55 * mm, 100 * mm]))
    s.append(Spacer(1, 12))

    s.append(Paragraph("SCHEDULE 2: PAYMENT PLAN", st["h"]))
    s.append(Paragraph(
        "The Buyer shall pay the Purchase Price in accordance with the following Payment Plan. Percentages are of the "
        "Purchase Price. Amounts are due on the Due Date stated, subject to Clause 3.4.", st["p"]))
    prow = [["No.", "Milestone", "% of Price", "Due Date", "Payment Trigger"]]
    for i, m in enumerate(t["payment_plan"], 1):
        prow.append([str(i), m["name"], pct(m["percent"]), long_date(m["due_date"]), m["trigger"]])
    s.append(table(prow, [10 * mm, 38 * mm, 20 * mm, 30 * mm, 62 * mm], repeat=1))
    s.append(Spacer(1, 14))
    s.append(Paragraph("EXECUTION", st["h"]))
    s.append(Paragraph(
        f"Signed by the parties on {long_date(t['spa_date'])}.", st["p"]))
    sig = [[f"For and on behalf of the Seller\n{t['developer']}\n\n______________________",
            f"The Buyer\n{t['buyer']}\n\n______________________"]]
    s.append(Table(sig, colWidths=[85 * mm, 85 * mm]))
    return s


def table(rows, widths, repeat=1):
    tb = Table(rows, colWidths=widths, repeatRows=repeat)
    tb.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (-1, 0), "Times-Bold"),
        ("FONTNAME", (0, 1), (-1, -1), "Times-Roman"),
        ("FONTSIZE", (0, 0), (-1, -1), 9.5),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]))
    # wrap cell text so long triggers break inside cells
    wrap = ParagraphStyle("c", fontName="Times-Roman", fontSize=9.5, leading=11.5)
    wrapb = ParagraphStyle("cb", fontName="Times-Bold", fontSize=9.5, leading=11.5)
    for r, row in enumerate(rows):
        for c, cell in enumerate(row):
            row[c] = Paragraph(str(cell), wrapb if r == 0 else wrap)
    return tb


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Times-Roman", 9)
    canvas.drawCentredString(A4[0] / 2, 12 * mm, f"Sale and Purchase Agreement - Page {doc.page}")
    canvas.restoreState()


def build_pdf(t: dict) -> Path:
    path = SAMPLES / t["file"]
    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=22 * mm, rightMargin=22 * mm,
                            topMargin=20 * mm, bottomMargin=22 * mm,
                            title=f"SPA {t['unit_id']}", author="Synthetic sample")
    doc.build(story_for(t, build_styles()), onFirstPage=footer, onLaterPages=footer)
    return path


def main() -> None:
    SAMPLES.mkdir(exist_ok=True)
    truth_out = {}
    for key, t in TRUTH.items():
        p = build_pdf(t)
        print("wrote", p.relative_to(ROOT))
        truth_out[t["file"]] = {k: v for k, v in t.items()
                                if k not in ("file", "project", "developer", "floor", "spa_date")}
    (ROOT / "ground_truth.json").write_text(json.dumps(truth_out, indent=2))
    print("wrote ground_truth.json")


if __name__ == "__main__":
    main()
