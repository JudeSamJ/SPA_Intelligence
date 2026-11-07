"""INTERNAL (company-side) routes: playbook review and ERP export/push. Never exposed to buyers."""
from __future__ import annotations

from datetime import date
from typing import Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field

from app import config, playbook as pb
from app.erp import d365
from app.statute_gap import effective_jurisdiction
from backend.api import auth, deps
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
def erp_push(contract_id: str, body: ErpPush, request: Request):
    src, c = deps.get_contract(contract_id)
    try:
        return d365.push(c, src.id, src.name, body.delay_days, body.as_of_date or date.today(), body.confirm,
                         auth.actor(request, body.reviewer), _paid(body))
    except d365.PushError as e:
        raise ApiError(409, "push_refused", str(e)) from None


class WebhookTest(BaseModel):
    kind: str = Field("contract_ready", pattern="^(contract_ready|alert|review_needed)$")


@router.post("/webhook/test")
def webhook_test(body: WebhookTest):
    """Send ONE test event (with the designed email) to the configured webhook, so a flow can be checked without extracting anything.
    Uses real data when the app has it, otherwise clearly labelled sample data."""
    import os
    from app import notifiers, obligations as ob
    from app.review import review_items
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        raise ApiError(409, "webhook_not_configured", "ALERT_WEBHOOK_URL is not set.")
    used = "real"
    items = [(s, deps.effective_contract(s)) for s in deps.list_sources()]
    items = [(s, c) for s, c in items if c is not None]
    if body.kind == "contract_ready":
        if items:
            s, c = items[0]
            data = {"contract": notifiers.contract_summary(s.id, s.name, c)}
        else:
            used, data = "sample", {"contract": {"contract_id": "", "contract_name": "sample_a.pdf", "unit_id": "MCR-1204", "buyer": "Sample Buyer",
                                                 "currency": "AED", "price": 2450000, "handover_date": "2027-06-30", "jurisdiction": "ae_dubai",
                                                 "milestones": 5, "payment_plan_percent_sum": 100.0, "warnings": 0, "needs_review": 0,
                                                 "plan": [{"name": f"Milestone {i}", "percent": 20, "due_date": None} for i in range(1, 6)]}}
    elif body.kind == "alert":
        al = ob.load_alerts()
        if al:
            a = al[0]
            data = {"alert": {k: a.get(k) for k in ("id", "contract_id", "contract_name", "event_type", "severity", "message", "due_date",
                                                      "days_until", "label")} | {"page": (a.get("evidence") or {}).get("page")}}
        else:
            used, data = "sample", {"alert": {"id": "sample", "contract_id": "", "contract_name": "sample_a.pdf", "event_type": "overdue",
                                              "severity": "high", "message": "Sample overdue payment", "due_date": "2026-03-15",
                                              "days_until": -237, "label": "Second Instalment (20%)", "page": 6}}
    else:
        q = [{"contract_id": s.id, "contract_name": s.name, **it} for s, c in items for it in review_items(c)]
        if q:
            r = q[0]
            data = {"review": {"contract_id": r["contract_id"], "contract_name": r["contract_name"], "field": r["field"],
                               "status": r.get("status"), "confidence": r.get("confidence"), "page": r.get("source_page")}}
        else:
            used, data = "sample", {"review": {"contract_id": "", "contract_name": "sample_a.pdf", "field": "price", "status": "partial",
                                               "confidence": 0.82, "page": 3}}
    hook = notifiers.WebhookNotifier(url, os.environ.get("ALERT_WEBHOOK_SECRET", ""))
    from app.emailcards import build_email
    email = build_email(body.kind, data)
    email["subject"] = "[TEST] " + email["subject"]
    ok = hook.post(body.kind, {**data, "email": email, "test": True})
    return {"sent": ok, "kind": body.kind, "data": used}
