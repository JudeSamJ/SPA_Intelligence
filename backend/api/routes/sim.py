"""Probabilistic simulation + portfolio rollup endpoints. Assumption-driven (see app/montecarlo.py)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import config
from app.montecarlo import parse_signal_csv, portfolio, public, sim_config, simulate_contract
from backend.api import deps
from backend.api.deps import ApiError
from backend.api.routes.trust import AmountPaid

router = APIRouter(tags=["simulation"])


class MCRequest(BaseModel):
    trials: Optional[int] = Field(None, ge=1, le=50000)
    seed: Optional[int] = Field(None, ge=0, le=2**31 - 1)
    family: Optional[Literal["triangular", "lognormal", "fixed"]] = None
    params: Optional[dict[str, float]] = None
    as_of_date: Optional[date] = None
    amounts_paid: Optional[list[AmountPaid]] = Field(None, max_length=60)
    signal_csv: Optional[str] = Field(None, max_length=20000)


def _dist(body: MCRequest) -> dict:
    cfg = sim_config()["delay_distribution"]
    dist = {k: (dict(v) if isinstance(v, dict) else v) for k, v in cfg.items()}
    if body.family:
        dist["family"] = body.family
    if body.params:
        allowed = set(dist[dist["family"]])
        bad = set(body.params) - allowed
        if bad:
            raise ApiError(422, "validation_error", f"Unknown parameter(s) for {dist['family']}: {', '.join(sorted(bad))}.")
        dist[dist["family"]].update(body.params)
    return dist


def _signal(body: MCRequest):
    try:
        return parse_signal_csv(body.signal_csv) if body.signal_csv else None
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e)) from None


@router.get("/simulation/defaults")
def defaults():
    return {**sim_config(), "label": "Assumption-driven defaults edited in rules/simulation.yaml"}


@router.post("/contracts/{contract_id}/montecarlo")
def montecarlo(contract_id: str, body: MCRequest | None = None):
    body = body or MCRequest()
    _, c = deps.get_contract(contract_id)
    try:
        r = simulate_contract(c, trials=body.trials, seed=body.seed, dist=_dist(body), as_of=body.as_of_date,
                              amounts_paid=[p.model_dump() for p in body.amounts_paid] if body.amounts_paid else None,
                              signal_rows=_signal(body))
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e)) from None
    return {**public(r), "disclaimer": config.DISCLAIMER}


@router.post("/portfolio/montecarlo")
def portfolio_montecarlo(body: MCRequest | None = None):
    body = body or MCRequest()
    items = []
    for src in deps.list_sources():
        c = deps.effective_contract(src)
        if c is not None:
            items.append((src.id, src.name, c))
    if not items:
        raise ApiError(409, "not_extracted", "No extracted contracts to roll up.")
    try:
        r = portfolio(items, trials=body.trials, seed=body.seed, dist=_dist(body), as_of=body.as_of_date,
                      signal_rows=_signal(body))
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e)) from None
    return {**r, "disclaimer": config.DISCLAIMER}
