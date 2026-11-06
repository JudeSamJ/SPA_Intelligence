import pytest

from app.penalty import (SimulationUnavailable, delay_penalty, delay_penalty_fixed_per_sqft,
                         simulate)
from app.schema import ContractData, Sourced


def sd(v):
    return Sourced(value=v, source_page=1, source_quote="q") if v is not None else Sourced()


def contract(basis="percent_per_annum", rate=6.0, grace=30, cap=None, price=1_000_000.0, area=1000.0):
    return ContractData(
        buyer=sd("B"), unit_id=sd("U"), price=sd(price), area_sqft=sd(area), handover_date=Sourced(),
        grace_period_days=sd(grace), delay_rate=sd(rate), delay_basis=sd(basis), delay_cap=sd(cap),
        payment_plan=[], cancellation_clause=Sourced())


def test_headline_example():
    # 1,000,000 * 6% * (90-30)/365 = 60,000 * 60/365 = 9,863.0137
    assert delay_penalty(1_000_000, 6, 90, 30) == 9863.01


def test_full_year_no_grace():
    assert delay_penalty(1_000_000, 6, 365) == 60000.00


def test_zero_delay():
    assert delay_penalty(1_000_000, 6, 0, 30) == 0.0


def test_delay_less_than_grace_and_equal_to_grace():
    assert delay_penalty(1_000_000, 6, 20, 30) == 0.0
    assert delay_penalty(1_000_000, 6, 30, 30) == 0.0


def test_one_day_past_grace():
    # 60,000 / 365 = 164.3835...
    assert delay_penalty(1_000_000, 6, 31, 30) == 164.38


def test_cap_applies():
    # uncapped: 1,000,000*6%*365/365 = 60,000 ; cap 5% = 50,000
    assert delay_penalty(1_000_000, 6, 365, 0, cap_pct=5) == 50000.00


def test_cap_not_reached():
    assert delay_penalty(1_000_000, 6, 90, 30, cap_pct=5) == 9863.01


def test_fixed_per_sqft():
    # 1,000 sqft * AED 7 * (120-90)/365 = 7000*30/365 = 575.3425
    assert delay_penalty_fixed_per_sqft(1000, 7, 120, 90) == 575.34


def test_fixed_per_sqft_within_grace():
    assert delay_penalty_fixed_per_sqft(1000, 7, 90, 90) == 0.0


def test_fixed_per_sqft_with_cap():
    # raw 1000*7*365/365 = 7,000 ; cap 0.5% of 1,000,000 = 5,000
    assert delay_penalty_fixed_per_sqft(1000, 7, 365, 0, price=1_000_000, cap_pct=0.5) == 5000.00


def test_negative_inputs_rejected():
    with pytest.raises(ValueError):
        delay_penalty(1_000_000, 6, -1)
    with pytest.raises(ValueError):
        delay_penalty(-5, 6, 10)


def test_simulate_percent_with_cap():
    rows = simulate(contract(cap=2.0, grace=60), [30, 90, 180, 365])
    # cap = 20,000
    assert [r["penalty"] for r in rows] == [0.0, 4931.51, 19726.03, 20000.0]
    assert [r["cap_reached"] for r in rows] == [False, False, False, True]
    assert rows[1]["chargeable_days"] == 30 and rows[1]["cap_amount"] == 20000.0


def test_simulate_fixed_basis():
    rows = simulate(contract(basis="fixed_per_sqft_per_year", rate=7.0, grace=90, area=1025.5), [30, 90, 180])
    # 1025.5*7 = 7178.5/yr ; 90 chargeable days -> 646,065/365 = 1770.04
    assert rows[0]["penalty"] == 0.0 and rows[1]["penalty"] == 0.0
    assert rows[2]["penalty"] == 1770.04


def test_simulate_unavailable_when_rate_missing_or_other_basis():
    with pytest.raises(SimulationUnavailable):
        simulate(contract(rate=None))
    with pytest.raises(SimulationUnavailable):
        simulate(contract(basis="other"))
