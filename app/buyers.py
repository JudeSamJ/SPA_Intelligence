"""Buyer assignments: which buyer identity (email or phone number) may ask about which contract.

Stored in the `buyer_assignments` table, so adding a buyer is one row, with no new key, no redeploy and no connector change.
A channel (Teams agent, WhatsApp adapter, web) authenticates itself with ONE service key and passes the buyer's identity;
the contract is then looked up here, never taken from the chat text.
"""
from __future__ import annotations

import re

from app import db

CHANNELS = ("any", "teams", "whatsapp", "web", "email", "api")
ID_RE = re.compile(r"^[0-9a-f]{64}$")


class BuyerError(ValueError):
    pass


def normalize_identity(raw: str) -> str:
    """Emails are lower-cased. Phone numbers keep a leading + and digits only. Anything else is rejected."""
    s = (raw or "").strip()
    if "@" in s:
        if not re.fullmatch(r"[^@\s]{1,64}@[^@\s]{1,190}\.[^@\s]{2,}", s):
            raise BuyerError("That does not look like an email address.")
        return s.lower()
    digits = re.sub(r"\D", "", s)
    if not (7 <= len(digits) <= 15):
        raise BuyerError("Enter an email address, or a phone number with country code.")
    return "+" + digits


def _need_db() -> None:
    if not db.enabled():
        raise BuyerError("Buyer assignments need the database (set DATABASE_URL).")


def assign(contract_id: str, identity: str, channel: str = "any", created_by: str = "") -> dict:
    _need_db()
    if not ID_RE.match(contract_id or ""):
        raise BuyerError("Invalid contract id.")
    if channel not in CHANNELS:
        raise BuyerError(f"Channel must be one of: {', '.join(CHANNELS)}.")
    ident = normalize_identity(identity)
    with db.connection() as cx:
        other = cx.execute("select contract_id from buyer_assignments where identity = %s and channel = %s and active "
                           "and contract_id <> %s", (ident, channel, contract_id)).fetchone()
        if other:
            raise BuyerError("That buyer is already assigned to a different contract. Remove that assignment first.")
        row = cx.execute(
            "insert into buyer_assignments (contract_id, identity, channel, created_by) values (%s,%s,%s,%s) "
            "on conflict (contract_id, identity, channel) do update set active = true "
            "returning id, contract_id, identity, channel, active, created_by, created_at",
            (contract_id, ident, channel, created_by[:80])).fetchone()
    return _row(row)


def _row(r) -> dict:
    return {"id": r[0], "contract_id": r[1], "identity": r[2], "channel": r[3], "active": r[4],
            "created_by": r[5], "created_at": r[6].isoformat(timespec="seconds")}


def list_assignments(contract_id: str | None = None) -> list[dict]:
    _need_db()
    sql = "select id, contract_id, identity, channel, active, created_by, created_at from buyer_assignments where active"
    args: tuple = ()
    if contract_id:
        sql, args = sql + " and contract_id = %s", (contract_id,)
    with db.connection() as cx:
        return [_row(r) for r in cx.execute(sql + " order by id", args).fetchall()]


def remove(assignment_id: int) -> bool:
    _need_db()
    with db.connection() as cx:
        return cx.execute("update buyer_assignments set active = false where id = %s and active",
                          (assignment_id,)).rowcount > 0


def contract_for_identity(identity: str, channel: str = "any") -> str | None:
    """The one contract this identity may ask about on this channel, else None."""
    if not db.enabled():
        return None
    try:
        ident = normalize_identity(identity)
    except BuyerError:
        return None
    with db.connection() as cx:
        rows = cx.execute("select distinct contract_id from buyer_assignments where identity = %s and active "
                          "and channel in (%s, 'any')", (ident, channel)).fetchall()
    return rows[0][0] if len(rows) == 1 else None          # none, or ambiguous: never guess


def record_audit(buyer: str, contract_id: str, channel: str, question: str, refused: bool, reason: str | None,
                 tool_calls: list, citation_pages: list) -> None:
    """Best effort: a database problem must never break an answer."""
    if not db.enabled():
        return
    import json
    try:
        with db.connection() as cx:
            cx.execute("insert into audit_log (buyer, contract_id, channel, question, refused, reason, tool_calls, citation_pages) "
                       "values (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb)",
                       (buyer[:64], contract_id, channel[:20], question[:500], refused, reason,
                        json.dumps(tool_calls, default=str), json.dumps(citation_pages, default=str)))
    except Exception:  # noqa: BLE001
        pass
