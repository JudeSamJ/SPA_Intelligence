"""Obligation watcher: derive dated obligations from a contract and classify them against an injected `as_of`.
Pure date logic (no clock reads inside the functions), so every case is testable.

Event types: due_soon, overdue, grace_expiring, handover_approaching, notice_deadline.
Caveats shown to the user: this tool does not know whether a payment was actually made, so 'overdue' means
'the due date has passed' (acknowledge the alert once handled). A clause anchored on the Notice of Completion
is dated from the contractual handover date (flagged `assumed_anchor`) because the real notice date is unknown.
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Protocol

import yaml

from . import config
from .schema import ContractData

log = logging.getLogger("spa.obligations")
EVENT_TYPES = ("due_soon", "overdue", "grace_expiring", "handover_approaching", "notice_deadline")


def settings() -> dict:
    return yaml.safe_load((config.RULES_DIR / "obligations.yaml").read_text())


def add_months(d: date, n: int) -> date:
    y, m = divmod(d.month - 1 + n, 12)
    y, m = d.year + y, m + 1
    return date(y, m, min(d.day, monthrange(y, m)[1]))


def _id(*parts) -> str:
    return hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def _evidence(item) -> dict:
    return {"page": item.source_page, "quote": item.source_quote}


def derive(c: ContractData, contract_id: str, name: str = "") -> list[dict]:
    """Obligations with a due date. No classification yet."""
    out: list[dict] = []
    cur = c.currency
    for i, m in enumerate(c.payment_plan, 1):
        if m.due_date is not None:
            amt = round(c.price.value * m.percent / 100, 2) if c.price.value is not None else None
            out.append({"kind": "payment", "label": f"{m.name} ({m.percent:g}%)", "due_date": m.due_date, "amount": amt,
                        "currency": cur, "field": f"payment_plan.{i}", "evidence": _evidence(m), "assumed_anchor": None})
    hd = c.handover_date.value
    if hd is not None:
        out.append({"kind": "handover", "label": "Contractual handover date", "due_date": hd, "amount": None,
                    "currency": cur, "field": "handover_date", "evidence": _evidence(c.handover_date), "assumed_anchor": None})
        if c.grace_period_days.value is not None:
            out.append({"kind": "grace_expiry", "label": f"Grace period ends ({c.grace_period_days.value} days after handover date)",
                        "due_date": hd + timedelta(days=c.grace_period_days.value), "amount": None, "currency": cur,
                        "field": "grace_period_days", "evidence": _evidence(c.grace_period_days), "assumed_anchor": None})
    for i, cl in enumerate(c.dated_clauses, 1):
        anchor, assumed = None, None
        if cl.anchor == "handover_date":
            anchor = hd
        elif cl.anchor == "grace_expiry" and hd is not None and c.grace_period_days.value is not None:
            anchor = hd + timedelta(days=c.grace_period_days.value)
        elif cl.anchor == "notice_of_completion" and hd is not None:
            anchor, assumed = hd, "Notice of Completion date unknown: dated from the contractual handover date."
        elif cl.anchor == "signing_date" and c.payment_plan and c.payment_plan[0].due_date:
            anchor, assumed = c.payment_plan[0].due_date, "Signing date taken from the first payment-plan date."
        if anchor is None:
            continue
        due = anchor + timedelta(days=cl.amount) if cl.unit == "days" else add_months(anchor, cl.amount)
        out.append({"kind": cl.kind, "label": f"{cl.description} ({cl.amount} {cl.unit})", "due_date": due, "amount": None,
                    "currency": cur, "field": f"dated_clauses.{i}", "evidence": _evidence(cl), "assumed_anchor": assumed})
    for o in out:
        o["contract_id"], o["contract_name"] = contract_id, name
        o["id"] = _id(contract_id, o["kind"], o["field"], o["due_date"])
    return out


def classify(o: dict, as_of: date, cfg: dict | None = None) -> dict:
    """Adds days_until, event_type (or None), status and severity."""
    cfg = cfg or settings()
    days = (o["due_date"] - as_of).days
    ev = None
    k = o["kind"]
    if k == "payment":
        ev = "overdue" if days < 0 else "due_soon" if days <= cfg["due_soon_days"] else None
    elif k == "handover":
        ev = "handover_approaching" if 0 <= days <= cfg["handover_approaching_days"] else None
    elif k == "grace_expiry":
        ev = "grace_expiring" if 0 <= days <= cfg["grace_expiring_days"] else None
    else:                                    # notice / cancellation right / defect liability / other
        ev = "notice_deadline" if 0 <= days <= cfg["notice_deadline_days"] else None
    status = ev or ("past" if days < 0 else "upcoming")
    return {**o, "due_date": o["due_date"].isoformat(), "days_until": days, "event_type": ev, "status": status,
            "severity": cfg["severity"][ev] if ev else "none"}


def obligations_for(c: ContractData, contract_id: str, name: str, as_of: date) -> list[dict]:
    cfg = settings()
    return sorted((classify(o, as_of, cfg) for o in derive(c, contract_id, name)), key=lambda o: o["due_date"])


def filter_obligations(rows: list[dict], within_days: Optional[int] = None, status: Optional[str] = None) -> list[dict]:
    out = rows
    if status:
        out = [r for r in out if r["status"] == status or r["event_type"] == status]
    if within_days is not None:
        out = [r for r in out if -10 ** 6 < r["days_until"] <= within_days]
    return out


# ------------------------------------------------------------------ alerts (in-app feed only)
class Notifier(Protocol):
    def notify(self, alert: dict) -> None: ...


class LoggingNotifier:
    """The only implementation in this task: writes to the log. No email, WhatsApp or SMS is sent."""

    def notify(self, alert: dict) -> None:
        log.info("alert %s %s %s", alert["event_type"], alert["severity"], alert["contract_id"][:8])


NOTIFIER: Notifier = LoggingNotifier()
_lock = threading.Lock()


def alerts_path() -> Path:
    return Path(config.ALERTS_PATH)


def load_alerts() -> list[dict]:
    p = alerts_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except ValueError:
            pass
    return []


def _save(alerts: list[dict]) -> None:
    p = alerts_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(alerts, indent=2))


def recompute(items: list[tuple[str, str, ContractData]], as_of: date) -> dict:
    """Rebuild the alert feed. New alerts go to the notifier; acknowledged ones keep their state; stale unacked
    alerts (condition no longer true) are removed."""
    with _lock:
        old = {a["id"]: a for a in load_alerts()}
        fresh: dict[str, dict] = {}
        for cid, name, c in items:
            for o in obligations_for(c, cid, name, as_of):
                if not o["event_type"]:
                    continue
                aid = _id(o["id"], o["event_type"])
                msg = _message(o)
                fresh[aid] = {"id": aid, "obligation_id": o["id"], "contract_id": cid, "contract_name": name,
                              "event_type": o["event_type"], "severity": o["severity"], "message": msg,
                              "due_date": o["due_date"], "days_until": o["days_until"], "label": o["label"],
                              "field": o["field"], "evidence": o["evidence"], "assumed_anchor": o["assumed_anchor"],
                              "created_at": old.get(aid, {}).get("created_at") or datetime.now(timezone.utc).isoformat(timespec="seconds"),
                              "acked": old.get(aid, {}).get("acked", False), "acked_at": old.get(aid, {}).get("acked_at"),
                              "as_of": as_of.isoformat()}
        new = [a for aid, a in fresh.items() if aid not in old]
        kept_acked = [a for aid, a in old.items() if a.get("acked") and aid not in fresh]
        result = list(fresh.values()) + kept_acked
        _save(result)
    for a in new:
        NOTIFIER.notify(a)
    return {"alerts": len(result), "new": len(new), "as_of": as_of.isoformat()}


def _message(o: dict) -> str:
    d = o["days_until"]
    when = f"{abs(d)} day(s) overdue" if d < 0 else "today" if d == 0 else f"in {d} day(s)"
    return f"{o['label']}: {o['event_type'].replace('_', ' ')}, due {o['due_date']} ({when})"


def ack(alert_id: str) -> dict | None:
    with _lock:
        alerts = load_alerts()
        for a in alerts:
            if a["id"] == alert_id:
                a["acked"], a["acked_at"] = True, datetime.now(timezone.utc).isoformat(timespec="seconds")
                _save(alerts)
                return a
    return None
