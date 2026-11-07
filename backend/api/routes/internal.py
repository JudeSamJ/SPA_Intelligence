"""INTERNAL (company-side) routes: playbook review and ERP export/push. Never exposed to buyers."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app import config, playbook as pb
from app.erp import d365
from app.statute_gap import effective_jurisdiction
from backend.api import deps
from backend.api.deps import ApiError
from backend.api.routes.trust import AmountPaid

router = APIRouter(tags=["internal"])


@router.get("/contracts/{contract_id}/playbook")
def playbook(contract_id: str, run_llm: bool = Query(False, description="Run the clause-specialist LLM (one call, cached)."),
             format: str = Query("json", pattern="^(json|csv)$")):
    src, c = deps.get_contract(contract_id)
    pdf = src.path.read_bytes()
    j = pb.load_cached(pdf)
    if j is None and run_llm:
        if not config.llm_configured():
            raise ApiError(503, "llm_not_configured", config.setup_hint())
        j = pb.judge_cached(pdf, pb.load_playbook())
    res = pb.evaluate(c, pdf, effective_jurisdiction(c), j)
    res["llm_run"] = j is not None
    if format == "csv":
        return PlainTextResponse(pb.to_csv(res), media_type="text/csv",
                                 headers={"Content-Disposition": f'attachment; filename="playbook_{src.id[:8]}.csv"'})
    return res


class ErpRequest(BaseModel):
    delay_days: Optional[int] = Field(None, ge=0, le=3650)
    as_of_date: Optional[date] = None
    amounts_paid: Optional[list[AmountPaid]] = Field(None, max_length=60)


class ErpPush(ErpRequest):
    confirm: bool = False
    reviewer: str = Field("", max_length=80)


def _paid(b):
    return [p.model_dump() for p in b.amounts_paid] if b.amounts_paid else None


@router.post("/contracts/{contract_id}/erp/export")
def erp_export(contract_id: str, body: ErpRequest | None = None):
    body = body or ErpRequest()
    src, c = deps.get_contract(contract_id)
    return d365.export(c, src.id, src.name, body.delay_days, body.as_of_date or date.today(), _paid(body))


@router.post("/contracts/{contract_id}/erp/push")
def erp_push(contract_id: str, body: ErpPush):
    src, c = deps.get_contract(contract_id)
    try:
        return d365.push(c, src.id, src.name, body.delay_days, body.as_of_date or date.today(), body.confirm,
                         body.reviewer, _paid(body))
    except d365.PushError as e:
        raise ApiError(409, "push_refused", str(e)) from None
