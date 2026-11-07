from __future__ import annotations

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Query

from app import config
from app import obligations as ob
from backend.api import deps
from backend.api.deps import ApiError

log = logging.getLogger("spa.api")
router = APIRouter(tags=["obligations"])


def _items():
    out = []
    for src in deps.list_sources():
        c = deps.effective_contract(src)
        if c is not None:
            out.append((src.id, src.name, c))
    return out


def recompute_now(as_of: date | None = None) -> dict:
    """Called by the daily scheduler and after any contract change (extraction, review, jurisdiction)."""
    try:
        return ob.recompute(_items(), as_of or date.today())
    except Exception as e:  # noqa: BLE001 (never break the request that triggered it)
        log.error("recompute failed: %s", type(e).__name__)
        return {"error": type(e).__name__}


@router.get("/obligations")
def obligations(as_of: Optional[date] = None, within_days: Optional[int] = Query(None, ge=0, le=3650),
                status: Optional[str] = None, contract_id: Optional[str] = None):
    as_of = as_of or date.today()
    rows = []
    for cid, name, c in _items():
        if contract_id and cid != contract_id:
            continue
        rows += ob.obligations_for(c, cid, name, as_of)
    rows.sort(key=lambda r: r["due_date"])
    return {"as_of": as_of.isoformat(), "obligations": ob.filter_obligations(rows, within_days, status),
            "event_types": list(ob.EVENT_TYPES), "disclaimer": config.DISCLAIMER,
            "caveat": "The tool does not know whether a payment was made: 'overdue' means the due date has passed."}


@router.get("/alerts")
def alerts(include_acked: bool = False):
    a = ob.load_alerts()
    shown = a if include_acked else [x for x in a if not x["acked"]]
    sev = {"high": 0, "medium": 1, "low": 2}
    shown.sort(key=lambda x: (sev.get(x["severity"], 3), x["due_date"]))
    return {"alerts": shown, "unacked": sum(1 for x in a if not x["acked"]), "delivery": "in-app feed only"}


@router.post("/alerts/recompute")
def alerts_recompute(as_of: Optional[date] = None):
    return recompute_now(as_of)


@router.post("/alerts/{alert_id}/ack")
def alert_ack(alert_id: str):
    a = ob.ack(alert_id)
    if a is None:
        raise ApiError(404, "not_found", "No such alert.")
    return a
