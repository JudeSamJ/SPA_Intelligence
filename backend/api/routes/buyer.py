"""Channel-agnostic buyer chat. A WhatsApp (or any other) adapter can call this later; none is built here."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field

from app import buyer, buyers, config
from app.agent import BuyerAgent
from backend.api import auth, deps
from backend.api.deps import ApiError
from backend.api.schemas import ChatTurn, Citation

router = APIRouter(prefix="/buyer", tags=["buyer"])


class BuyerChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    channel: str = Field("api", max_length=20)


class BuyerChatResponse(BaseModel):
    answer: str
    refused: bool
    reason: str | None = None
    tool_calls: list[str]
    citations: list[Citation]
    disclaimer: str = config.DISCLAIMER


class BuyerMe(BaseModel):
    linked: bool
    contract_name: str | None = None


@router.get("/me", response_model=BuyerMe)
def buyer_me(request: Request):
    """For the buyer's own page: the name of the contract they may ask about (never its id or any content)."""
    p = auth.current_principal(request)
    cid = auth.contract_for_principal(p) if p is not None else None
    if cid is None:
        return BuyerMe(linked=False)
    try:
        return BuyerMe(linked=True, contract_name=deps.get_source(cid).name)
    except ApiError:
        return BuyerMe(linked=False)


@router.post("/chat", response_model=BuyerChatResponse, dependencies=[Depends(deps.chat_limiter)])
def buyer_chat(body: BuyerChatRequest, request: Request, authorization: str | None = Header(None)):
    """AUTH_MODE=entra: an Entra token with the Spa.Buyer role, mapped to ONE contract in BUYER_ACCOUNTS.
    AUTH_MODE=off: the BUYER_TOKENS stub. Either way the contract comes from the identity, never from the request."""
    p = auth.current_principal(request)
    if p is not None and auth.CHANNEL in p.roles:
        who_raw = request.headers.get("x-buyer-identity", "").strip()
        cid = buyers.contract_for_identity(who_raw, body.channel) if who_raw else None
        if cid is None:
            raise ApiError(403, "forbidden", "This buyer is not linked to a contract.")
        who = "buyer:" + buyers.normalize_identity(who_raw)
    elif p is not None:
        cid = auth.contract_for_principal(p)
        if cid is None:
            raise ApiError(403, "forbidden", "This account is not linked to a contract.")
        who = "entra:" + p.oid
    else:
        if not buyer.load_tokens():
            raise ApiError(503, "buyer_access_not_configured", "Buyer access is not configured (set BUYER_TOKENS).")
        who = (authorization or "").removeprefix("Bearer ").strip()
        cid = buyer.contract_for_token(who)
        if cid is None:
            raise ApiError(401, "unauthorized", "Missing or invalid buyer token.")
    _, c = deps.get_contract(cid)                      # scoped: the contract comes from the identity, never from the request
    r = BuyerAgent(c).ask(body.message, history=[t.model_dump() for t in body.history])
    buyer.audit(who, cid, body.message, r, body.channel)
    return BuyerChatResponse(answer=r.answer, refused=r.refused, reason=r.reason, tool_calls=r.tool_calls,
                             citations=[Citation(**x) for x in r.citations])
