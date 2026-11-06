from __future__ import annotations

from fastapi import APIRouter

from app import config
from app.penalty import SimulationUnavailable, simulate
from backend.api import deps
from backend.api.deps import ApiError
from backend.api.schemas import PenaltyRequest, PenaltyResponse, PenaltyRow, PenaltyTerms

router = APIRouter(prefix="/contracts", tags=["penalty"])


@router.post("/{contract_id}/penalty", response_model=PenaltyResponse)
def penalty(contract_id: str, body: PenaltyRequest | None = None):
    _, c = deps.get_contract(contract_id)
    rules = config.load_rules()
    defaults = rules["penalty"]["scenarios_days"]
    scenarios = body.scenarios if body and body.scenarios else defaults
    if any(d < 0 or d > 3650 for d in scenarios):
        raise ApiError(422, "validation_error", "Scenario days must be between 0 and 3650.")
    try:
        rows = simulate(c, scenarios, rules)
    except SimulationUnavailable as e:
        raise ApiError(422, "simulation_unavailable", str(e)) from None
    return PenaltyResponse(
        terms=PenaltyTerms(rate=c.delay_rate, basis=c.delay_basis, grace_days=c.grace_period_days,
                           cap_pct=c.delay_cap, price=c.price, area_sqft=c.area_sqft),
        day_count_basis=rules["penalty"]["day_count_basis"], default_scenarios=defaults,
        rows=[PenaltyRow(**r) for r in rows])
