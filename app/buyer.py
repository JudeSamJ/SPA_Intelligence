"""Buyer access: simple token auth STUB (BUYER_TOKENS maps token -> contract id) and an audit log.

STUB: tokens live in the environment, there is no login, expiry, rotation or user store. Production auth is out of scope.
Every request is scoped server-side to the one contract bound to the token; the agent's tools take no contract id.
The audit log records question, tool calls (name + scalar args) and the answer, truncated, with no contract text
(no source quotes) and never the token itself (only a short hash).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from . import config

ID_RE = re.compile(r"^[0-9a-f]{64}$")


def load_tokens() -> dict[str, str]:
    """BUYER_TOKENS = JSON object {"token": "contract_id"} or "token=contract_id,token2=contract_id2"."""
    raw = os.environ.get("BUYER_TOKENS", "").strip()
    out: dict[str, str] = {}
    if not raw:
        return out
    if raw.startswith("{"):
        try:
            data = json.loads(raw)
        except ValueError:
            return {}
        pairs = data.items()
    else:
        pairs = (p.split("=", 1) for p in re.split(r"[,;\s]+", raw) if "=" in p)
    for tok, cid in pairs:
        tok, cid = str(tok).strip(), str(cid).strip()
        if len(tok) >= 8 and ID_RE.match(cid):
            out[tok] = cid
    return out


def contract_for_token(token: str | None) -> str | None:
    """Constant-time comparison against every configured token."""
    if not token:
        return None
    found = None
    for t, cid in load_tokens().items():
        if hmac.compare_digest(t.encode(), token.encode()):
            found = cid
    return found


def audit_dir() -> Path:
    return Path(os.environ.get("SPA_AUDIT_DIR") or config.ROOT / "data" / "audit")


def audit(token: str, contract_id: str, question: str, reply, channel: str = "api") -> None:
    d = audit_dir()
    d.mkdir(parents=True, exist_ok=True)
    entry = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "buyer": hashlib.sha256(token.encode()).hexdigest()[:10], "contract_id": contract_id, "channel": channel,
             "question": question[:500], "tool_calls": reply.tool_log, "refused": reply.refused, "reason": reply.reason,
             "citation_pages": [c["page"] for c in reply.citations], "answer": reply.answer[:500]}
    with open(d / "buyer_chat.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
