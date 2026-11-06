from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent import BuyerAgent
from backend.api import deps
from backend.api.schemas import ChatRequest, ChatResponse, Citation

router = APIRouter(prefix="/contracts", tags=["chat"])


@router.post("/{contract_id}/chat", response_model=ChatResponse, dependencies=[Depends(deps.chat_limiter)])
def chat(contract_id: str, body: ChatRequest):
    _, c = deps.get_contract(contract_id)
    history = [t.model_dump() for t in body.history]
    r = BuyerAgent(c).ask(body.message, history=history)     # sync: runs in FastAPI's threadpool
    return ChatResponse(answer=r.answer, refused=r.refused, tool_calls=r.tool_calls,
                        citations=[Citation(**x) for x in r.citations])
