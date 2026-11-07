"""TEST-ONLY helpers: a fake Anthropic client that returns tool output built from ground_truth.json.
Never used by the app or the eval; it exists to exercise the pipeline offline."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.extract import locate_quote, pdf_pages

ROOT = Path(__file__).resolve().parent.parent
TRUTH = json.loads((ROOT / "ground_truth.json").read_text())


def _long(iso):
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def oracle_input(pdf_path: Path) -> dict:
    t = TRUTH[pdf_path.name]
    pages = pdf_pages(pdf_path.read_bytes())

    def S(value, quote):
        if quote is None:
            return {"value": None, "source_page": None, "source_quote": None}
        pg = locate_quote(pages, quote)
        assert pg, f"test quote not in PDF: {quote}"
        return {"value": value, "source_page": pg, "source_quote": quote}

    cur = t.get("currency", "AED")
    basis_q = (f"{t['delay_rate']:g}% per annum" if t["delay_basis"] == "percent_per_annum"
               else f"{cur} {t['delay_rate']:.2f} per square foot")
    cap_q = (f"shall not exceed {t['delay_cap']:g}% of the Purchase Price" if t["delay_cap"] is not None
             else "is not subject to any cap or maximum limit")
    plan = []
    for m in t["payment_plan"]:
        q = f"{m['name']} {m['percent']:g}% {_long(m['due_date'])} {m['trigger']}"   # whole table row, as printed
        plan.append({"name": m["name"], "percent": m["percent"], "due_date": m["due_date"],
                     "trigger": m["trigger"], "source_page": locate_quote(pages, q), "source_quote": q})
    return {
        "buyer": S(t["buyer"], t["buyer"]),
        "unit_id": S(t["unit_id"], t["unit_id"]),
        "price": S(float(t["price"]), f"{cur} {t['price']:,}"),
        "area_sqft": S(t["area_sqft"], f"{t['area_sqft']:,.2f} square feet"),
        "handover_date": S(t["handover_date"], _long(t["handover_date"])),
        "grace_period_days": S(t["grace_period_days"], f"{t['grace_period_days']} days"),
        "delay_rate": S(t["delay_rate"], basis_q),
        "delay_basis": S(t["delay_basis"], basis_q),
        "delay_cap": S(t["delay_cap"], cap_q),
        "payment_plan": plan,
        "cancellation_clause": S("Buyer may cancel and be refunded after prolonged delay"
                                 if t["has_cancellation_clause"] else None,
                                 "Buyer's right to cancel for delay" if t["has_cancellation_clause"] else None),
    }


class FakeClient:
    """Returns the queued tool inputs in order, one per messages.create call."""

    def __init__(self, *tool_inputs):
        self.queue = list(tool_inputs)
        self.calls = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.calls.append(kw)
        inp = self.queue.pop(0)
        block = SimpleNamespace(type="tool_use", name="record_contract_terms", id=f"tu_{len(self.calls)}", input=inp)
        return SimpleNamespace(content=[block])
