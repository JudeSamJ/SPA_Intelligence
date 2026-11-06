from __future__ import annotations

from datetime import date

from fastapi import APIRouter

from app import config
from app.cashflow import CashflowUnavailable, at_risk_summary, build_schedule
from backend.api import deps
from backend.api.deps import ApiError
from backend.api.routes.contracts import _plan
from backend.api.schemas import AtRisk, CashflowRequest, CashflowResponse, Period

router = APIRouter(prefix="/contracts", tags=["cashflow"])


@router.post("/{contract_id}/cashflow", response_model=CashflowResponse)
def cashflow(contract_id: str, body: CashflowRequest | None = None):
    _, c = deps.get_contract(contract_id)
    body = body or CashflowRequest()
    rules = config.load_rules()
    today = date.today()
    try:
        df, unscheduled = build_schedule(c, body.granularity, as_of=today, rules=rules)
        risk = at_risk_summary(c, body.delay_days, rules)
    except CashflowUnavailable as e:
        raise ApiError(422, "cashflow_unavailable", str(e)) from None
    plan_by_name = {p.milestone: p for p in _plan(c)}
    return CashflowResponse(
        granularity=body.granularity, as_of=today, price=c.price.value,
        periods=[Period(**r) for r in df.to_dict("records")],
        unscheduled=[plan_by_name[u["milestone"]] for u in unscheduled],
        at_risk=AtRisk(**risk), at_risk_definition=" ".join(rules["cashflow"]["at_risk"]["definition"].split()),
        max_delay_days=max(rules["penalty"]["scenarios_days"]))
