"""Statute gap: hand-calculated cases. Rates come from the ILLUSTRATIVE fixture table
(tests/fixtures/rates/sbi_mclr.yaml: 8.50% from 2020-01-01, 9.00% from 2025-02-01). Spread = 2.0 (pack)."""
from datetime import date
from pathlib import Path

import pytest

from app.schema import ContractData, Milestone, Sourced
from app.statute_gap import compute_gap, derive_payments, effective_jurisdiction

FIX = Path(__file__).parent / "fixtures" / "rates"


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setenv("SPA_RATES_DIR", str(FIX))


def S(v):
    return Sourced(value=v, source_page=1, source_quote="x") if v is not None else Sourced()


def contract(price=1_000_000.0, cap=10.0, grace=30, handover=date(2025, 1, 1), rate=6.0, plan=()):
    return ContractData(buyer=S("B"), unit_id=S("U"), price=S(price), area_sqft=S(1000.0), handover_date=S(handover),
                        grace_period_days=S(grace), delay_rate=S(rate), delay_basis=S("percent_per_annum"),
                        delay_cap=S(cap) if cap is not None else Sourced(), payment_plan=list(plan),
                        cancellation_clause=Sourced())


PAID = [{"date": date(2024, 6, 1), "amount": 400_000}, {"date": date(2024, 9, 1), "amount": 300_000}]


def test_hand_calc_single_rate_period():
    # possession 2025-01-01, delay 31 days -> ends 2025-02-01, all inside the 8.50% period: rate 8.5+2 = 10.5%
    # statutory = 700,000 x 10.5% x 31/365 = 73,500 x 31 / 365 = 2,278,500 / 365 = 6,242.47
    # contractual: grace 30 -> 1 chargeable day: 1,000,000 x 6% x 1/365 = 164.38
    # shortfall = 6,242.47 - 164.38 = 6,078.09
    r = compute_gap(contract(), 31, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["can_compute"]
    assert r["statutory"]["amount"] == 6242.47
    assert r["contractual"]["penalty"] == 164.38
    assert r["shortfall"] == 6078.09 and r["one_sided"] is True
    assert r["amounts_paid_source"] == "user" and r["amounts_paid_total"] == 700_000
    assert r["unreviewed"] is True


def test_hand_calc_rate_change_splits_period():
    # delay 100 days from 2025-01-01 -> ends 2025-04-11. 2025-01-01..2025-02-01 = 31 days at 10.5%
    # 2025-02-01..2025-04-11 = 69 days at (9.0+2)=11.0%.  700,000 x (0.105 x 31 + 0.11 x 69) / 365
    # = 700,000 x (3.255 + 7.59) / 365 = 7,591,500 / 365 = 20,799.99... exact: 20,798.63
    r = compute_gap(contract(), 100, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["statutory"]["amount"] == 20798.63
    segs = r["statutory"]["payments"][0]["segments"]
    assert [s["days"] for s in segs] == [31, 69] and [s["rate_pct"] for s in segs] == [10.5, 11.0]
    # contractual: 70 chargeable days: 1,000,000 x 6% x 70/365 = 4,200,000/365 = 11,506.85
    assert r["contractual"]["penalty"] == 11506.85
    assert r["shortfall"] == round(20798.63 - 11506.85, 2) == 9291.78


def test_zero_delay_everything_zero():
    r = compute_gap(contract(), 0, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["statutory"]["amount"] == 0 and r["contractual"]["penalty"] == 0
    assert r["shortfall"] == 0 and r["one_sided"] is False and r["findings"] == []


def test_delay_within_grace_contract_zero_statute_positive():
    # delay 20 days <= grace 30: contractual 0. statutory = 700,000 x 10.5% x 20/365 = 1,470,000/365 = 4,027.40
    r = compute_gap(contract(), 20, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["contractual"]["penalty"] == 0 and r["statutory"]["amount"] == 4027.40
    assert r["shortfall"] == 4027.40 and r["one_sided"]
    assert any(f["code"] == "grace_period_not_in_statute" for f in r["findings"])


def test_cap_binds():
    # cap 1% of 1,000,000 = 10,000. Uncapped contractual (70 days) = 11,506.85 -> capped at 10,000.00
    # statutory (100 days) = 20,798.63 ; shortfall = 10,798.63
    r = compute_gap(contract(cap=1.0), 100, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["contractual"]["penalty"] == 10000.0 and r["contractual"]["cap_reached"]
    assert r["shortfall"] == 10798.63
    assert any(f["code"] == "cap_binds_below_statute" for f in r["findings"])


def test_contract_more_favourable_not_flagged():
    r = compute_gap(contract(rate=40.0, cap=None, grace=0), 31, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["shortfall"] < 0 and r["one_sided"] is False and not r["findings"]


def test_payment_after_possession_accrues_from_payment_date():
    # 100,000 paid 2025-01-11 (10 days after possession), delay 31 -> accrues 2025-01-11..2025-02-01 = 21 days at 10.5%
    # 100,000 x 10.5% x 21/365 = 220,500/365 = 604.11
    r = compute_gap(contract(), 31, date(2025, 3, 1), [{"date": date(2025, 1, 11), "amount": 100_000}], pack_id="in_rera")
    assert r["statutory"]["amount"] == 604.11


def test_as_of_excludes_later_payments():
    r = compute_gap(contract(), 31, date(2024, 7, 1), PAID, pack_id="in_rera")
    counted = [p for p in r["statutory"]["payments"] if p["counted"]]
    assert len(counted) == 1 and counted[0]["amount"] == 400_000
    # 400,000 x 10.5% x 31/365 = 1,302,000/365 = 3,567.12
    assert r["statutory"]["amount"] == 3567.12


def test_derived_from_plan():
    plan = [Milestone(name="Booking", percent=20, due_date=date(2024, 6, 1), source_page=1, source_quote="x"),
            Milestone(name="Later", percent=80, due_date=date(2026, 1, 1), source_page=1, source_quote="x")]
    c = contract(plan=plan)
    assert [p["amount"] for p in derive_payments(c, date(2025, 1, 1))] == [200_000.0]
    r = compute_gap(c, 31, date(2025, 1, 1), None, pack_id="in_rera")
    assert r["amounts_paid_source"] == "payment_plan"
    # 200,000 x 10.5% x 31/365 = 651,000/365 = 1,783.56
    assert r["statutory"]["amount"] == 1783.56


def test_missing_rate_row_cannot_compute(monkeypatch, tmp_path):
    (tmp_path / "sbi_mclr.yaml").write_text("id: sbi_mclr\nname: t\nrows: []\n")
    monkeypatch.setenv("SPA_RATES_DIR", str(tmp_path))
    r = compute_gap(contract(), 31, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["can_compute"] is False and "no rate in effect" in r["reason"]


def test_rate_table_starting_after_possession_cannot_compute(monkeypatch, tmp_path):
    (tmp_path / "sbi_mclr.yaml").write_text("id: sbi_mclr\nname: t\nrows:\n  - {effective_from: '2026-01-01', rate_pct: 9}\n")
    monkeypatch.setenv("SPA_RATES_DIR", str(tmp_path))
    r = compute_gap(contract(), 31, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["can_compute"] is False and "earliest row: 2026-01-01" in r["reason"]


def test_dubai_pack_has_no_formula_cannot_compute():
    r = compute_gap(contract(), 31, date(2025, 1, 1), PAID, pack_id="ae_dubai")
    assert r["can_compute"] is False and r["needs_legal_review"] and "no statutory" in r["reason"]


def test_missing_possession_date():
    r = compute_gap(contract(handover=None), 31, date(2025, 1, 1), PAID, pack_id="in_rera")
    assert r["can_compute"] is False and "possession" in r["reason"]


def test_no_payments_cannot_compute():
    r = compute_gap(contract(), 31, date(2025, 1, 1), None, pack_id="in_rera")
    assert r["can_compute"] is False and "No amounts paid" in r["reason"]


def test_effective_jurisdiction_priority():
    c = contract()
    assert effective_jurisdiction(c) == "ae_dubai"
    c.jurisdiction_detected = S("in_rera")
    assert effective_jurisdiction(c) == "in_rera"
    c.jurisdiction = "ae_dubai"
    assert effective_jurisdiction(c) == "ae_dubai"


def test_bad_delay_rejected():
    with pytest.raises(ValueError):
        compute_gap(contract(), -1, date(2025, 1, 1), PAID, pack_id="in_rera")
