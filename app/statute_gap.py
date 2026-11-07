"""Penalty vs statute gap. Pure Python (Decimal), no LLM.

contractual   = existing simulator (app/penalty.py) for the delay scenario
statutory     = pack formula `interest_on_amounts_paid`:
                for each payment p (paid on or before as_of):
                    accrues from max(payment date, agreed possession date) to possession + delay_days,
                    at (base rate from the DATED table in effect each day + spread) per annum / day_count.
shortfall     = statutory - contractual   (positive = contract is less favourable than statute: "one-sided")

If anything needed is missing (pack rule, rate row, possession date, price) the result is
{"can_compute": false, "reason": ...}. Nothing is guessed.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from . import config
from .packs import Pack, PackEntry, RateUnavailable, load_pack, load_rate_table
from .penalty import SimulationUnavailable, penalty_for_contract
from .schema import ContractData

TOL = Decimal("0.005")


def _q(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def _cannot(reason: str, **extra) -> dict:
    return {"can_compute": False, "reason": reason, **extra}


def effective_jurisdiction(c: ContractData) -> str:
    return c.jurisdiction or c.jurisdiction_detected.value or config.DEFAULT_RULES


def derive_payments(c: ContractData, as_of: date) -> list[dict]:
    """Payments implied by the payment plan: milestones with a due date on or before as_of."""
    if c.price.value is None:
        return []
    out = []
    for i, m in enumerate(c.payment_plan, 1):
        if m.due_date is not None and m.due_date <= as_of:
            out.append({"date": m.due_date, "amount": round(c.price.value * m.percent / 100, 2),
                        "label": m.name, "field": f"payment_plan.{i}"})
    return out


def statutory_interest(payments: list[dict], possession: date, delay_days: int, as_of: date,
                       spread_pct: float, base_table, day_count: int) -> dict:
    """Interest on amounts paid. Returns total + a per-payment breakdown. Raises RateUnavailable."""
    end = possession + timedelta(days=delay_days)
    spread = Decimal(str(spread_pct))
    rows, total = [], Decimal(0)
    for p in payments:
        pd = p["date"]
        if pd > as_of or pd >= end:
            rows.append({**p, "counted": False, "days": 0, "interest": 0.0,
                         "note": "paid after the as-of date" if pd > as_of else "paid after the delay period ended"})
            continue
        start = max(pd, possession)
        interest, days, parts = Decimal(0), 0, []
        for s, e, base in base_table.segments(start, end):
            n = (e - s).days
            rate = Decimal(str(base)) + spread
            part = Decimal(str(p["amount"])) * rate / 100 * n / day_count
            interest += part
            days += n
            parts.append({"from": s.isoformat(), "to": e.isoformat(), "days": n, "base_pct": base,
                          "rate_pct": float(rate), "interest": _q(part)})
        total += interest
        rows.append({**p, "counted": True, "accrues_from": start.isoformat(), "days": days,
                     "interest": _q(interest), "segments": parts})
    return {"total": _q(total), "payments": rows, "end": end.isoformat()}


def _severity(shortfall: Decimal, statutory: Decimal, rules: dict) -> str:
    sev = rules["gap"]["severity"]
    ratio = shortfall / statutory if statutory > 0 else Decimal(0)
    if ratio >= Decimal(str(sev["high_if_shortfall_ratio_gte"])):
        return "high"
    if ratio >= Decimal(str(sev["medium_if_shortfall_ratio_gte"])):
        return "medium"
    return "low"


def _inputs(c: ContractData, entry: PackEntry, f: dict, base_table, pay_source: str, as_of: date, delay_days: int) -> list[dict]:
    def row(label, value, field=None, source="contract"):
        return {"label": label, "value": value, "field": field, "source": source}
    return [
        row("Agreed possession date", c.handover_date.value, "handover_date"),
        row("Purchase price", c.price.value, "price"),
        row("Contract delay rate", c.delay_rate.value, "delay_rate"),
        row("Contract grace period (days)", c.grace_period_days.value, "grace_period_days"),
        row("Contract cap (% of price)", c.delay_cap.value, "delay_cap"),
        row("Delay scenario (days)", delay_days, source="user"),
        row("As-of date", as_of, source="user"),
        row("Amounts paid source", pay_source, source="user" if pay_source == "user" else "payment plan"),
        row("Statute", f"{entry.statute}, {entry.section}", source="pack"),
        row("Rate table", f"{base_table.name}" + (" (ILLUSTRATIVE)" if base_table.illustrative else ""), source="rate table"),
        row("Spread (percentage points)", f["rate"]["spread_pct"], source="pack"),
        row("Day count", f["day_count"], source="pack"),
    ]


def compute_gap(c: ContractData, delay_days: int, as_of: date, amounts_paid: Optional[list[dict]] = None,
                pack_id: Optional[str] = None, rules: Optional[dict] = None) -> dict:
    if delay_days < 0 or delay_days > 3650:
        raise ValueError("delay_days must be between 0 and 3650")
    pack_id = pack_id or effective_jurisdiction(c)
    try:
        pack: Pack = load_pack(pack_id)
    except KeyError:
        return _cannot(f"Unknown jurisdiction pack '{pack_id}'.", jurisdiction=pack_id)
    rules = rules or config.load_rules(pack.id)
    base = {"jurisdiction": pack.id, "currency": pack.currency, "pack_version": pack.version}
    entry = pack.formula_entry("interest_on_amounts_paid")
    if entry is None:
        todo = pack.entry("ae_delay_compensation")
        return _cannot("This jurisdiction pack has no statutory delay-interest formula"
                       + (" (the rule is a TODO that needs legal review)." if todo else "."),
                       needs_legal_review=True, entry=_entry_meta(todo) if todo else None, **base)
    f = entry.formula
    meta = _entry_meta(entry)
    possession = c.handover_date.value
    if possession is None:
        return _cannot("The contract does not state an agreed possession date.", entry=meta, **base)
    try:
        table = load_rate_table(f["rate"]["base_table"])
    except RateUnavailable as e:
        return _cannot(str(e), entry=meta, **base)
    if amounts_paid:
        payments = [{"date": p["date"], "amount": float(p["amount"]), "label": p.get("label") or "payment",
                     "field": None} for p in amounts_paid]
        source = "user"
    else:
        payments = derive_payments(c, as_of)
        source = "payment_plan"
        if not payments:
            return _cannot("No amounts paid: enter payments, or give a payment plan with dated milestones on or "
                           "before the as-of date.", entry=meta, **base)
    try:
        stat = statutory_interest(payments, possession, delay_days, as_of, f["rate"]["spread_pct"], table,
                                  f.get("day_count", 365))
    except RateUnavailable as e:
        return _cannot(str(e), entry=meta, **base)

    contractual, contract_reason = None, None
    try:
        contractual = penalty_for_contract(c, delay_days, rules)
    except SimulationUnavailable as e:
        contract_reason = str(e)
    out = {"can_compute": True, **base, "delay_days": delay_days, "as_of": as_of.isoformat(),
           "possession_date": possession.isoformat(), "delay_ends": stat["end"],
           "amounts_paid_source": source, "amounts_paid_total": round(sum(p["amount"] for p in payments if p["date"] <= as_of), 2),
           "statutory": {"amount": stat["total"], "payments": _jsonable(stat["payments"]),
                         "rate_table": {"id": table.id, "name": table.name, "illustrative": table.illustrative,
                                        "source": table.source, "rows": [{"effective_from": d.isoformat(), "rate_pct": r}
                                                                         for d, r in table.sorted_rows()]},
                         "spread_pct": f["rate"]["spread_pct"]},
           "contractual": contractual, "contractual_reason": contract_reason,
           "entry": meta, "unreviewed": entry.unreviewed or entry.needs_legal_review,
           "inputs": _jsonable(_inputs(c, entry, f, table, source, as_of, delay_days)), "findings": []}
    if contractual is None:
        out["shortfall"], out["one_sided"] = None, None
        out["note"] = f"Contractual penalty could not be computed: {contract_reason}"
        return out
    short = Decimal(str(stat["total"])) - Decimal(str(contractual["penalty"]))
    out["shortfall"] = _q(short)
    out["one_sided"] = short > TOL
    if out["one_sided"]:
        sev = _severity(short, Decimal(str(stat["total"])), rules)
        out["findings"].append({
            "code": "delay_compensation_below_statute", "severity": sev, "field": "delay_rate",
            "message": f"Contractual delay compensation is {out['shortfall']:,.2f} {pack.currency} below the "
                       f"statutory entitlement for this scenario.",
            "evidence_fields": ["delay_rate", "grace_period_days", "delay_cap"]})
        if contractual["cap_reached"]:
            out["findings"].append({
                "code": "cap_binds_below_statute", "severity": "high", "field": "delay_cap",
                "message": "The contractual cap is reached; the statutory interest has no such cap in this model.",
                "evidence_fields": ["delay_cap"]})
        if (c.grace_period_days.value or 0) > 0 and not f.get("respects_contract_grace", False):
            out["findings"].append({
                "code": "grace_period_not_in_statute", "severity": "low", "field": "grace_period_days",
                "message": "The contract grants a grace period before compensation accrues; the pack formula "
                           "accrues from the agreed possession date (TODO lawyer: confirm).",
                "evidence_fields": ["grace_period_days"]})
    return out


def _entry_meta(e: PackEntry) -> dict:
    return {"id": e.id, "statute": e.statute, "section": e.section, "description": e.description,
            "effective_from": e.effective_from.isoformat() if e.effective_from else None,
            "source_url": e.source_url, "reviewed_by_lawyer": e.reviewed_by_lawyer,
            "needs_legal_review": e.needs_legal_review}


def _jsonable(x):
    if isinstance(x, dict):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_jsonable(v) for v in x]
    if isinstance(x, date):
        return x.isoformat()
    return x
