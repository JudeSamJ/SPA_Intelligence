"""Deterministic delay-penalty calculators. Pure Python, no LLM.

Units: rates and caps are PERCENT numbers (6 means 6%, 10 means 10% of price).
Semantics (configurable day-count in rules/common.yaml and the jurisdiction pack): compensation accrues only on days
of delay *after* the grace period; days <= grace_days give zero. Results are rounded
half-up to 2 decimals.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from . import config
from .schema import ContractData


class SimulationUnavailable(ValueError):
    """The contract lacks a term needed to simulate (message says which)."""


def _d(x) -> Decimal:
    return Decimal(str(x))


def _q(x: Decimal) -> float:
    return float(x.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def chargeable_days(delay_days: int, grace_days: int = 0) -> int:
    if delay_days < 0 or grace_days < 0:
        raise ValueError("delay_days and grace_days must be >= 0")
    return max(0, delay_days - grace_days)


def _apply_cap(amount: Decimal, price, cap_pct: Optional[float]) -> Decimal:
    if cap_pct is None:
        return amount
    if cap_pct < 0:
        raise ValueError("cap_pct must be >= 0")
    return min(amount, _d(price) * _d(cap_pct) / 100)


def delay_penalty(price: float, annual_rate: float, delay_days: int, grace_days: int = 0,
                  cap_pct: Optional[float] = None, day_count: int = 365) -> float:
    """Interest-style delay compensation on the purchase price.

    penalty = price * annual_rate% * chargeable_days / day_count, capped at cap_pct% of price.
    Example: 1,000,000 at 6% with 90 days delay and 30 grace -> 9,863.01.
    """
    if price < 0 or annual_rate < 0:
        raise ValueError("price and annual_rate must be >= 0")
    days = chargeable_days(delay_days, grace_days)
    raw = _d(price) * _d(annual_rate) / 100 * days / day_count
    return _q(_apply_cap(raw, price, cap_pct))


def delay_penalty_fixed_per_sqft(area_sqft: float, rate_per_sqft_per_year: float, delay_days: int,
                                 grace_days: int = 0, price: Optional[float] = None,
                                 cap_pct: Optional[float] = None, day_count: int = 365) -> float:
    """Fixed compensation per sq ft per year: area * rate * chargeable_days / day_count.

    A cap (percent of price) applies only if both price and cap_pct are given.
    """
    if area_sqft < 0 or rate_per_sqft_per_year < 0:
        raise ValueError("area_sqft and rate must be >= 0")
    days = chargeable_days(delay_days, grace_days)
    raw = _d(area_sqft) * _d(rate_per_sqft_per_year) * days / day_count
    if price is not None:
        raw = _apply_cap(raw, price, cap_pct)
    return _q(raw)


def penalty_for_contract(contract: ContractData, delay_days: int, rules: dict | None = None) -> dict:
    """Penalty for one delay scenario using the contract's extracted terms. Raises SimulationUnavailable."""
    rules = rules or config.load_rules()
    dc = rules["penalty"]["day_count_basis"]
    basis = contract.delay_basis.value
    rate = contract.delay_rate.value
    if basis not in ("percent_per_annum", "fixed_per_sqft_per_year"):
        raise SimulationUnavailable(f"Delay basis is '{basis}'; only percent_per_annum and "
                                    f"fixed_per_sqft_per_year can be simulated.")
    if rate is None:
        raise SimulationUnavailable("The contract does not state a delay rate.")
    grace = contract.grace_period_days.value or 0
    cap = contract.delay_cap.value
    if basis == "percent_per_annum":
        if contract.price.value is None:
            raise SimulationUnavailable("The contract does not state a price.")
        amount = delay_penalty(contract.price.value, rate, delay_days, grace, cap, dc)
    else:
        if contract.area_sqft.value is None:
            raise SimulationUnavailable("The contract does not state the area (sq ft).")
        amount = delay_penalty_fixed_per_sqft(contract.area_sqft.value, rate, delay_days, grace,
                                              contract.price.value, cap, dc)
    cap_amount = (round(contract.price.value * cap / 100, 2)
                  if cap is not None and contract.price.value is not None else None)
    return {
        "delay_days": delay_days,
        "grace_days": grace,
        "chargeable_days": chargeable_days(delay_days, grace),
        "penalty": amount,
        "cap_amount": cap_amount,
        "cap_reached": cap_amount is not None and amount >= cap_amount,
        "pct_of_price": (round(amount / contract.price.value * 100, 3) if contract.price.value else None),
    }


def simulate(contract: ContractData, scenarios: list[int] | None = None, rules: dict | None = None) -> list[dict]:
    """Penalty table for several delay scenarios (default from rules/common.yaml and the jurisdiction pack)."""
    rules = rules or config.load_rules()
    scenarios = scenarios if scenarios is not None else rules["penalty"]["scenarios_days"]
    return [penalty_for_contract(contract, d, rules) for d in scenarios]
