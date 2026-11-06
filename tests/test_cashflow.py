from datetime import date

import pytest

from app.cashflow import (period_end, CashflowUnavailable, at_risk_summary, build_schedule, classify_milestone,
                          next_payment, period_key)
from app.schema import ContractData, Milestone, Sourced


def sd(v):
    return Sourced(value=v, source_page=1, source_quote="q") if v is not None else Sourced()


def ms(name, pct, d, trigger=None):
    return Milestone(name=name, percent=pct, due_date=d, trigger=trigger, source_page=1, source_quote=name)


def contract(plan, price=1_000_000.0, **kw):
    base = dict(buyer=sd("B"), unit_id=sd("U"), price=sd(price), area_sqft=sd(1000.0), handover_date=Sourced(),
                grace_period_days=sd(0), delay_rate=sd(6.0), delay_basis=sd("percent_per_annum"),
                delay_cap=sd(None), payment_plan=plan, cancellation_clause=Sourced())
    base.update(kw)
    return ContractData(**base)


PLAN = [
    ms("Booking", 20, date(2026, 1, 15), "On signing"),
    ms("Second", 20, date(2026, 2, 20), "Six months after signing"),
    ms("Slab", 30, date(2026, 5, 10), "On completion of podium slab"),
    ms("Handover", 30, date(2026, 12, 31), "On notice of completion and handover"),
]


def test_classification():
    assert classify_milestone(PLAN[0]) == "time_based"
    assert classify_milestone(PLAN[2]) == "construction_linked"
    assert classify_milestone(PLAN[3]) == "handover_linked"


def test_period_keys():
    assert period_key(date(2026, 5, 10), "quarter") == "2026-Q2"
    assert period_key(date(2026, 5, 10), "month") == "2026-05"
    with pytest.raises(ValueError):
        period_key(date(2026, 1, 1), "week")


def test_quarterly_schedule_amounts():
    df, un = build_schedule(contract(PLAN), "quarter")
    assert un == []
    assert list(df["period"]) == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    assert list(df["amount_due"]) == [400000.0, 300000.0, 0.0, 300000.0]
    assert list(df["at_risk_amount"]) == [0.0, 300000.0, 0.0, 300000.0]
    assert list(df["safe_amount"]) == [400000.0, 0.0, 0.0, 0.0]
    assert list(df["cumulative"]) == [400000.0, 700000.0, 700000.0, 1000000.0]
    assert df["cumulative_pct"].iloc[-1] == 100.0


def test_empty_periods_filled_with_zero():
    plan = [ms("A", 50, date(2026, 1, 10)), ms("B", 50, date(2026, 10, 10))]
    df, _ = build_schedule(contract(plan), "quarter")
    assert list(df["period"]) == ["2026-Q1", "2026-Q2", "2026-Q3", "2026-Q4"]
    assert list(df["amount_due"]) == [500000.0, 0.0, 0.0, 500000.0]
    assert list(df["cumulative"]) == [500000.0] * 3 + [1000000.0]
    dm, _ = build_schedule(contract(plan), "month")
    assert len(dm) == 10


def test_monthly_schedule():
    df, _ = build_schedule(contract(PLAN), "month")
    assert len(df) == 12 and df["period"].iloc[0] == "2026-01" and df["period"].iloc[-1] == "2026-12"
    assert df["amount_due"].sum() == 1_000_000.0


def test_period_end():
    assert period_end("2026-Q2") == date(2026, 6, 30) and period_end("2024-02") == date(2024, 2, 29)


def test_is_past_flag():
    df, _ = build_schedule(contract(PLAN), "quarter", as_of=date(2026, 6, 1))
    assert list(df["is_past"]) == [True, False, False, False]


def test_undated_milestones_are_unscheduled_not_invented():
    plan = PLAN[:3] + [ms("Handover", 30, None, "On handover")]
    df, un = build_schedule(contract(plan), "quarter")
    assert df["amount_due"].sum() == 700000.0
    assert [u["milestone"] for u in un] == ["Handover"] and un[0]["amount"] == 300000.0


def test_percent_sum_not_100_still_computes_amounts():
    plan = [ms("A", 50, date(2026, 1, 1)), ms("B", 45, date(2026, 6, 1), "completion of foundation")]
    df, _ = build_schedule(contract(plan), "quarter")
    assert df["amount_due"].sum() == 950000.0


def test_at_risk_summary_with_penalty():
    # linked = 300k + 300k = 600k ; penalty 1,000,000*6%*180/365 = 29,589.04 (no grace, no cap)
    s = at_risk_summary(contract(PLAN), 180)
    assert s["linked_amount"] == 600000.0
    assert s["penalty_exposure"] == 29589.04
    assert s["at_risk_total"] == 629589.04
    assert s["linked_pct_of_plan"] == 60.0


def test_at_risk_zero_delay():
    assert at_risk_summary(contract(PLAN), 0)["penalty_exposure"] == 0.0


def test_at_risk_when_penalty_unavailable():
    s = at_risk_summary(contract(PLAN, delay_basis=sd("other")), 90)
    assert s["penalty_exposure"] is None and s["penalty_note"]
    assert s["at_risk_total"] == 600000.0


def test_missing_price_or_plan():
    with pytest.raises(CashflowUnavailable):
        build_schedule(contract(PLAN, price=None))
    with pytest.raises(CashflowUnavailable):
        build_schedule(contract([]))


def test_next_payment():
    assert next_payment(contract(PLAN), date(2026, 3, 1)).name == "Slab"
    assert next_payment(contract(PLAN), date(2026, 5, 10)).name == "Slab"  # due today counts
    assert next_payment(contract(PLAN), date(2027, 1, 1)) is None
