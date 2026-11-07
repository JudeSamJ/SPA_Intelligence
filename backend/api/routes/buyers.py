"""Staff: link a buyer (email or phone) to a contract. Reviewers can change assignments; Staff can read them."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app import buyers
from backend.api import auth, deps
from backend.api.deps import ApiError

router = APIRouter(prefix="/buyers", tags=["buyers"])


class AssignRequest(BaseModel):
    contract_id: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    identity: str = Field(..., min_length=3, max_length=200, description="Buyer's email address or phone number with country code.")
    channel: str = Field("any", max_length=20)


def _wrap(fn, *a, **kw):
    try:
        return fn(*a, **kw)
    except buyers.BuyerError as e:
        raise ApiError(409 if "already assigned" in str(e) else 422, "buyer_error", str(e)) from None


@router.get("")
def list_buyers(contract_id: str | None = None):
    if contract_id:
        deps.get_source(contract_id)
    return {"assignments": _wrap(buyers.list_assignments, contract_id)}


@router.post("", status_code=201)
def assign(body: AssignRequest, request: Request):
    deps.get_source(body.contract_id)
    return _wrap(buyers.assign, body.contract_id, body.identity, body.channel, auth.actor(request))


@router.delete("/{assignment_id}")
def unassign(assignment_id: int):
    if not _wrap(buyers.remove, assignment_id):
        raise ApiError(404, "not_found", "Assignment not found.")
    return {"removed": assignment_id}
