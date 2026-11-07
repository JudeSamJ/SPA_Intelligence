"""Channel-agnostic buyer chat. A WhatsApp (or any other) adapter can call this later; none is built here."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field

from app import buyer, config
from app.agent import BuyerAgent
from backend.api import deps
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


@router.post("/chat", response_model=BuyerChatResponse, dependencies=[Depends(deps.chat_limiter)])
def buyer_chat(body: BuyerChatRequest, authorization: str | None = Header(None)):
    if not buyer.load_tokens():
        raise ApiError(503, "buyer_access_not_configured", "Buyer access is not configured (set BUYER_TOKENS).")
    token = (authorization or "").removeprefix("Bearer ").strip()
    cid = buyer.contract_for_token(token)
    if cid is None:
        raise ApiError(401, "unauthorized", "Missing or invalid buyer token.")
    _, c = deps.get_contract(cid)                      # scoped: the contract comes from the token, never from the request
    r = BuyerAgent(c).ask(body.message, history=[t.model_dump() for t in body.history])
    buyer.audit(token, cid, body.message, r, body.channel)
    return BuyerChatResponse(answer=r.answer, refused=r.refused, reason=r.reason, tool_calls=r.tool_calls,
                             citations=[Citation(**x) for x in r.citations])
