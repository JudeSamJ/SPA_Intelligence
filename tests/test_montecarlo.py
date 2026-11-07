from datetime import date
from pathlib import Path

import numpy as np
import pytest

from app.montecarlo import draw_delays, parse_signal_csv, portfolio, signal_shift, simulate_contract
from app.penalty import penalty_for_contract
from app.statute_gap import compute_gap
from tests.test_statute_gap import PAID, S, contract  # noqa: F401  (helpers + rates fixture below)

FIX = Path(__file__).parent / "fixtures" / "rates"
CFG = {"trials": 2000, "seed": 7, "max_trials": 50000, "signal": {"days_per_gap_point": 4.0, "max_shift_days": 180},
       "delay_distribution": {"family": "triangular", "triangular": {"min_days": 0, "mode_days": 60, "max_days": 365},
                              "lognormal": {"median_days": 90, "sigma": 0.6}, "fixed": {"days": 90}}}


@pytest.fixture(autouse=True)
def rates(monkeypatch):
    monkeypatch.setenv("SPA_RATES_DIR", str(FIX))


def india():
    c = contract()
    c.jurisdiction = "in_rera"
    return c


def test_same_seed_reproducible_and_different_seed_differs():
    a = draw_delays(CFG["delay_distribution"], 1000, 5)
    b = draw_delays(CFG["delay_distribution"], 1000, 5)
    c = draw_delays(CFG["delay_distribution"], 1000, 6)
    assert (a == b).all() and not (a == c).all()
    r1 = simulate_contract(india(), cfg=CFG, as_of=date(2025, 1, 1), amounts_paid=PAID)
    r2 = simulate_contract(india(), cfg=CFG, as_of=date(2025, 1, 1), amounts_paid=PAID)
    assert {k: v for k, v in r1.items() if k != "_vectors"} == {k: v for k, v in r2.items() if k != "_vectors"}


def test_degenerate_distribution_equals_deterministic_simulator():
    dist = {"family": "fixed", "fixed": {"days": 100}}
    c = india()
    r = simulate_contract(c, cfg=CFG, dist=dist, trials=500, as_of=date(2025, 1, 1), amounts_paid=PAID)
    det_c = penalty_for_contract(c, 100)["penalty"]
    det_s = compute_gap(c, 100, date(2025, 1, 1), PAID, pack_id="in_rera")["statutory"]["amount"]
    assert r["contractual"]["p10"] == r["contractual"]["p50"] == r["contractual"]["p90"] == det_c == 11506.85
    assert r["statutory"]["p50"] == det_s == 20798.63
    assert r["shortfall"]["p50"] == round(det_s - det_c, 2)
    assert r["delay_days"]["p50"] == 100 and r["prob_delay_exceeds_grace"] == 1.0


def test_percentile_ordering_and_probabilities():
    r = simulate_contract(india(), cfg=CFG, as_of=date(2025, 1, 1), amounts_paid=PAID)
    for key in ("delay_days", "contractual", "statutory", "shortfall"):
        s = r[key]
        assert s["p10"] <= s["p50"] <= s["p90"], key
    qs = [q["contractual"] for q in r["quantiles"]]
    assert qs == sorted(qs)
    assert 0 < r["prob_delay_exceeds_grace"] < 1
    # triangular(0,60,365), grace 30: P(delay>30) analytically = 1 - (30^2)/(365*60) = 0.959 (rounded days, tolerance)
    assert abs(r["prob_delay_exceeds_grace"] - (1 - 30 ** 2 / (365 * 60))) < 0.03
    assert r["assumption_driven"] is True and "not a prediction" in r["label"]


def test_cap_probability_and_dubai_has_no_statute():
    c = contract(cap=0.5)       # cap = 5,000; binds once contractual > 5,000 (> ~43 chargeable days)
    r = simulate_contract(c, cfg=CFG, as_of=date(2025, 1, 1), amounts_paid=PAID, pack_id="ae_dubai")
    assert r["prob_cap_binds"] > 0.3 and r["statutory"] is None and "no statutory" in r["unavailable_reason"]


def test_signal_csv_shift_rule_and_validation():
    rows = parse_signal_csv("date,planned_progress_pct,actual_progress_pct\n2025-01-01,40,38\n2025-02-01,50,44\n")
    s = signal_shift(rows, CFG["signal"])
    assert s["gap_points"] == 6 and s["shift_days"] == 24 and not s["clamped"]       # 6 points x 4 days
    assert signal_shift(parse_signal_csv("date,planned_progress_pct,actual_progress_pct\n2025-01-01,90,10"),
                        CFG["signal"])["shift_days"] == 180                          # 80 x 4 = 320 -> clamped to 180
    base = draw_delays(CFG["delay_distribution"], 1000, 3)
    shifted = draw_delays(CFG["delay_distribution"], 1000, 3, 24.0)
    assert (shifted >= base).all() and shifted.sum() > base.sum()
    with pytest.raises(ValueError, match="columns"):
        parse_signal_csv("a,b\n1,2")
    with pytest.raises(ValueError, match="line 2"):
        parse_signal_csv("date,planned_progress_pct,actual_progress_pct\nnot-a-date,1,2")


def test_bad_inputs():
    with pytest.raises(ValueError):
        draw_delays({"family": "triangular", "triangular": {"min_days": 10, "mode_days": 5, "max_days": 20}}, 10, 1)
    with pytest.raises(ValueError):
        draw_delays({"family": "zzz"}, 10, 1)
    with pytest.raises(ValueError, match="trials"):
        simulate_contract(india(), cfg=CFG, trials=10 ** 7)


def test_portfolio_rollup_never_mixes_currencies():
    a, b = india(), contract(price=500_000.0)
    b.currency = "AED"; b.jurisdiction = "ae_dubai"
    a.currency = "INR"
    p = portfolio([("1", "inr", a), ("2", "aed", b), ("3", "inr2", india())], cfg=CFG, as_of=date(2025, 1, 1))
    assert set(p["totals_by_currency"]) == {"INR", "AED"}
    inr = p["totals_by_currency"]["INR"]
    assert inr["contracts"] == 2
    # common draws: two identical contracts -> total = exactly 2x a single contract
    single = [r for r in p["rows"] if r["contract_id"] == "1"][0]["contractual"]
    assert inr["contractual"]["p50"] == pytest.approx(2 * single["p50"], abs=0.02)
