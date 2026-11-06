"""Deterministic cash-flow schedule and "at risk" exposure. Pure Python, no LLM.

DEFINITION OF "AT RISK" (configurable in rules/uae.yaml -> cashflow.at_risk):

    at_risk_total = linked_amount + penalty_exposure

* linked_amount: sum of payment-plan amounts (percent/100 * price) whose milestone name or
  trigger text contains a construction or handover keyword from the rules file
  (e.g. "foundation", "slab", "handover"). These payments depend on the developer actually
  delivering a construction stage, so they are exposed to delay.
* penalty_exposure: the delay compensation computed by app.penalty for a chosen delay
  scenario (days). It is reported separately as well, because it is compensation the buyer
  could be owed rather than money the buyer pays; the combined figure follows the product
  definition and both parts are always shown.

Milestones without a stated due date are never given an invented date; they are returned
in `unscheduled` and excluded from the period table.
"""
from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

import pandas as pd

from . import config
from .penalty import SimulationUnavailable, penalty_for_contract
from .schema import ContractData, Milestone


class CashflowUnavailable(ValueError):
    pass


def classify_milestone(m: Milestone, rules: dict | None = None) -> str:
    """'handover_linked' | 'construction_linked' | 'time_based' via keywords in name+trigger."""
    rules = rules or config.load_rules()
    cfg = rules["cashflow"]["at_risk"]
    text = f"{m.name} {m.trigger or ''}".lower()
    if any(k.lower() in text for k in cfg["handover_keywords"]):
        return "handover_linked"
    if any(k.lower() in text for k in cfg["construction_keywords"]):
        return "construction_linked"
    return "time_based"


def period_key(d: date, period: str) -> str:
    if period == "month":
        return f"{d.year}-{d.month:02d}"
    if period == "quarter":
        return f"{d.year}-Q{(d.month - 1) // 3 + 1}"
    raise ValueError("period must be 'month' or 'quarter'")


def period_end(key: str) -> date:
    """Last calendar day of a period key such as '2026-05' or '2026-Q2'."""
    year = int(key[:4])
    if "Q" in key:
        month = int(key[-1]) * 3
    else:
        month = int(key[5:7])
    return date(year, month, calendar.monthrange(year, month)[1])


def _all_periods(first: date, last: date, period: str) -> list[str]:
    """Every period key from first to last inclusive (so empty periods show as zero)."""
    y, m = first.year, first.month
    keys: list[str] = []
    while (y, m) <= (last.year, last.month):
        k = period_key(date(y, m, 1), period)
        if not keys or keys[-1] != k:
            keys.append(k)
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return keys


def milestone_rows(contract: ContractData, rules: dict | None = None) -> list[dict]:
    """One row per milestone with its AED amount and classification."""
    price = contract.price.value
    if price is None:
        raise CashflowUnavailable("The contract does not state a price.")
    if not contract.payment_plan:
        raise CashflowUnavailable("No payment plan was extracted.")
    rows = []
    for m in contract.payment_plan:
        kind = classify_milestone(m, rules)
        rows.append({
            "milestone": m.name, "percent": m.percent, "amount": round(price * m.percent / 100, 2),
            "due_date": m.due_date, "trigger": m.trigger, "type": kind,
            "at_risk": kind != "time_based", "source_page": m.source_page,
        })
    return rows


def build_schedule(contract: ContractData, period: str | None = None, as_of: Optional[date] = None,
                   rules: dict | None = None) -> tuple[pd.DataFrame, list[dict]]:
    """Return (period table, unscheduled milestones).

    Period table columns: period, amount_due, at_risk_amount, safe_amount, cumulative, cumulative_pct, is_past (period ended before as_of).
    """
    rules = rules or config.load_rules()
    period = period or rules["cashflow"]["default_period"]
    rows = milestone_rows(contract, rules)
    scheduled = [r for r in rows if r["due_date"] is not None]
    unscheduled = [r for r in rows if r["due_date"] is None]
    price = contract.price.value
    agg: dict[str, dict] = {}
    if scheduled:
        first, last = min(r["due_date"] for r in scheduled), max(r["due_date"] for r in scheduled)
        for k in _all_periods(first, last, period):
            agg[k] = {"period": k, "amount_due": 0.0, "at_risk_amount": 0.0, }
    for r in sorted(scheduled, key=lambda r: r["due_date"]):
        k = period_key(r["due_date"], period)
        a = agg[k]
        a["amount_due"] += r["amount"]
        a["at_risk_amount"] += r["amount"] if r["at_risk"] else 0.0
    df = pd.DataFrame(list(agg.values()), columns=["period", "amount_due", "at_risk_amount"])
    if not df.empty:
        df["amount_due"] = df["amount_due"].round(2)
        df["at_risk_amount"] = df["at_risk_amount"].round(2)
        df["safe_amount"] = (df["amount_due"] - df["at_risk_amount"]).round(2)
        df["cumulative"] = df["amount_due"].cumsum().round(2)
        df["cumulative_pct"] = (df["cumulative"] / price * 100).round(2)
        df["is_past"] = df["period"].apply(lambda k: period_end(k) < as_of) if as_of else False
    return df, unscheduled


def at_risk_summary(contract: ContractData, delay_days: int | None = None, rules: dict | None = None) -> dict:
    """linked_amount, penalty_exposure for the chosen delay scenario, and their sum (see module docstring)."""
    rules = rules or config.load_rules()
    if delay_days is None:
        delay_days = rules["cashflow"]["default_delay_scenario_days"]
    rows = milestone_rows(contract, rules)
    linked = round(sum(r["amount"] for r in rows if r["at_risk"]), 2)
    total_plan = round(sum(r["amount"] for r in rows), 2)
    try:
        pen = penalty_for_contract(contract, delay_days, rules)["penalty"]
        note = None
    except SimulationUnavailable as e:
        pen, note = None, str(e)
    return {
        "delay_days": delay_days,
        "linked_amount": linked,
        "linked_pct_of_plan": round(linked / total_plan * 100, 2) if total_plan else None,
        "penalty_exposure": pen,
        "penalty_note": note,
        "at_risk_total": round(linked + (pen or 0.0), 2),
        "plan_total": total_plan,
    }


def next_payment(contract: ContractData, as_of: date) -> Optional[Milestone]:
    """Earliest dated milestone due on or after as_of (None if none)."""
    upcoming = [m for m in contract.payment_plan if m.due_date and m.due_date >= as_of]
    return min(upcoming, key=lambda m: m.due_date) if upcoming else None
