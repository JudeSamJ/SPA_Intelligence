"""Trust routes: evidence boxes, page images, human review, jurisdiction packs, statute gap."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app import config
from app.evidence import locate, render_page_png
from app.packs import list_packs, load_pack
from app.review import ReviewError, add_decision, export_golden, get_item, load_store, review_items, save_store, valid_field
from app.schema import ContractData, Evidence, Sourced
from app.statute_gap import compute_gap, effective_jurisdiction
from backend.api import auth, deps
from backend.api.deps import ApiError

router = APIRouter(tags=["trust"])


class EvidenceResponse(BaseModel):
    field: str
    value: Any = None
    evidence: Evidence
    grounding_status: Optional[str] = None
    confidence: Optional[float] = None
    human_verified: bool = False


@router.get("/contracts/{contract_id}/evidence/{field:path}", response_model=EvidenceResponse)
def evidence(contract_id: str, field: str):
    src, c = deps.get_contract(contract_id)
    try:
        item = get_item(c, field) if valid_field(field) else (c.jurisdiction_detected if field == "jurisdiction" else None)
    except ReviewError as e:
        raise ApiError(404, "not_found", str(e)) from None
    if item is None:
        raise ApiError(404, "not_found", f"Unknown field '{field}'.")
    ev = item.evidence or locate(src.path.read_bytes(), item.source_page, item.source_quote)
    val = item.value if isinstance(item, Sourced) else item.name
    return EvidenceResponse(field=field, value=val, evidence=ev,
                            grounding_status=item.grounding.status if item.grounding else None,
                            confidence=item.confidence, human_verified=item.human_verified)


@router.get("/contracts/{contract_id}/locate", response_model=Evidence)
def locate_quote_endpoint(contract_id: str, page: int = Query(1, ge=1), quote: str = Query(..., max_length=1000)):
    """Highlight rectangles for any quote (used for chat citations)."""
    src = deps.get_source(contract_id)
    return locate(src.path.read_bytes(), page, quote)


@router.get("/contracts/{contract_id}/page/{page}.png")
def page_image(contract_id: str, page: int, scale: float = Query(1.5, ge=0.5, le=3)):
    src = deps.get_source(contract_id)
    if not 1 <= page <= src.pages:
        raise ApiError(404, "not_found", "No such page.")
    return Response(render_page_png(src.path.read_bytes(), page, scale), media_type="image/png",
                    headers={"Cache-Control": "private, max-age=3600"})


# ------------------------------------------------------------------ review
class ReviewRequest(BaseModel):
    action: Literal["accept", "correct", "reject"]
    value: Any = None
    note: str = Field("", max_length=500)
    reviewer: str = Field("", max_length=80)
    source_page: Optional[int] = Field(None, ge=1)
    source_quote: Optional[str] = Field(None, max_length=1000)


@router.post("/contracts/{contract_id}/fields/{field:path}/review")
def review_field(contract_id: str, field: str, body: ReviewRequest, request: Request):
    src, c = deps.get_contract(contract_id)
    try:
        d = add_decision(c, src.id, field, body.action, body.value, body.note, auth.actor(request, body.reviewer),
                         body.source_page, body.source_quote)
    except (ReviewError, ValueError) as e:
        raise ApiError(422, "validation_error", str(e)) from None
    from backend.api.routes.obligations import recompute_now
    recompute_now()
    from backend.api import persistence
    persistence.flush_soon()                                      # keep the human decision in the database
    return {"saved": d, "disclaimer": config.DISCLAIMER}


@router.get("/contracts/{contract_id}/reviews")
def reviews(contract_id: str):
    src = deps.get_source(contract_id)
    return {"decisions": load_store(src.id)["decisions"]}


@router.get("/review-queue")
def review_queue():
    out = []
    for src in deps.list_sources():
        c = deps.effective_contract(src)
        if c is None:
            continue
        for it in review_items(c):
            out.append({"contract_id": src.id, "contract_name": src.name, **it})
    out.sort(key=lambda r: (r["confidence"] if r["confidence"] is not None else 0))
    return {"items": out, "count": len(out)}


@router.post("/contracts/{contract_id}/golden-export")
def golden_export(contract_id: str, allow_partial: bool = False):
    src, c = deps.get_contract(contract_id)
    try:
        d = export_golden(c, src.id, src.path, config.ROOT / "eval" / "golden", allow_partial)
    except ReviewError as e:
        raise ApiError(409, "review_pending", str(e)) from None
    return {"path": str(d.relative_to(config.ROOT)), "doc_id": d.name}


# ------------------------------------------------------------------ jurisdiction + packs
class JurisdictionBody(BaseModel):
    jurisdiction: Optional[str] = None


@router.put("/contracts/{contract_id}/jurisdiction")
def set_jurisdiction(contract_id: str, body: JurisdictionBody):
    src, _ = deps.get_contract(contract_id)
    if body.jurisdiction is not None:
        try:
            load_pack(body.jurisdiction)
        except KeyError:
            raise ApiError(422, "validation_error", "Unknown jurisdiction pack.") from None
    store = load_store(src.id)
    store["jurisdiction"] = body.jurisdiction
    save_store(src.id, store)
    _, c = deps.get_contract(contract_id)
    return {"jurisdiction": effective_jurisdiction(c)}


@router.get("/packs")
def packs():
    out = []
    for p in list_packs():
        out.append({"id": p.id, "name": p.name, "country": p.country, "currency": p.currency, "version": p.version,
                    "entries": [{**e.model_dump(mode="json"), "unreviewed": e.unreviewed} for e in p.entries]})
    return {"packs": out, "disclaimer": config.DISCLAIMER}


# ------------------------------------------------------------------ statute gap
class AmountPaid(BaseModel):
    date: date
    amount: float = Field(ge=0)
    label: Optional[str] = Field(None, max_length=80)


class GapRequest(BaseModel):
    delay_days: int = Field(..., ge=0, le=3650)
    as_of_date: Optional[date] = None
    amounts_paid: Optional[list[AmountPaid]] = Field(None, max_length=60)
    jurisdiction: Optional[str] = None


@router.post("/contracts/{contract_id}/statute-gap")
def statute_gap(contract_id: str, body: GapRequest):
    src, c = deps.get_contract(contract_id)
    paid = [p.model_dump() for p in body.amounts_paid] if body.amounts_paid else None
    pack = body.jurisdiction or effective_jurisdiction(c)
    r = compute_gap(c, body.delay_days, body.as_of_date or date.today(), paid, pack_id=pack,
                    rules=config.load_rules(pack) if _pack_ok(pack) else None)
    # evidence refs for each contract-sourced input, so the UI can open the highlight
    ev = {}
    for f in ("handover_date", "price", "delay_rate", "grace_period_days", "delay_cap"):
        it = getattr(c, f)
        ev[f] = {"page": it.source_page, "quote": it.source_quote, "has_box": bool(it.evidence and it.evidence.bbox)}
    return {**r, "evidence": ev, "disclaimer": config.DISCLAIMER}


def _pack_ok(pack: str) -> bool:
    try:
        load_pack(pack)
        return True
    except KeyError:
        return False
