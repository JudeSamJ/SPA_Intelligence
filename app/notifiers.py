"""Outbound notifications for Power Automate (or any HTTPS webhook). Opt-in: nothing is sent unless ALERT_WEBHOOK_URL is set.

A Power Automate flow starting with "When an HTTP request is received" gives you a URL; put it in ALERT_WEBHOOK_URL. The flow then
sends the Teams/email/WhatsApp message. We never contact end users ourselves.

Payloads carry identifiers, dates, severity and page numbers, never contract text or quotes. Each request is signed
(X-SPA-Signature: sha256=HMAC(secret, timestamp + "." + body)) so the flow can reject forged calls. Delivery failures are logged
by type and never raise: a webhook outage must not break extraction or review.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx

from . import config
from .obligations import LoggingNotifier

log = logging.getLogger("spa.notify")


def sign(secret: str, ts: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), ts.encode() + b"." + body, hashlib.sha256).hexdigest()


def verify(secret: str, ts: str, body: bytes, signature: str, max_age: int = 300, now: float | None = None) -> bool:
    """For the receiving side / tests: constant-time check plus a replay window."""
    try:
        if abs((now or time.time()) - float(ts)) > max_age:
            return False
    except ValueError:
        return False
    return hmac.compare_digest(sign(secret, ts, body), signature)


def _safe_url(url: str) -> bool:
    u = urlparse(url)
    return u.scheme == "https" or (u.scheme == "http" and u.hostname in ("localhost", "127.0.0.1"))


class WebhookNotifier:
    transport: httpx.BaseTransport | None = None      # tests inject a mock transport

    def __init__(self, url: str, secret: str = "", timeout: float = 10.0):
        if not _safe_url(url):
            raise ValueError("ALERT_WEBHOOK_URL must be https (http only for localhost).")
        self.url, self.secret, self.timeout = url, secret, timeout

    def post(self, kind: str, data: dict) -> bool:
        body = json.dumps({"type": kind, "sent_at": time.time(), **data}, separators=(",", ":")).encode()
        ts = str(int(time.time()))
        headers = {"Content-Type": "application/json", "X-SPA-Timestamp": ts}
        if self.secret:
            headers["X-SPA-Signature"] = sign(self.secret, ts, body)
        try:
            with httpx.Client(timeout=self.timeout, transport=self.transport) as c:
                r = c.post(self.url, content=body, headers=headers)
            ok = 200 <= r.status_code < 300
            if not ok:
                log.warning("webhook %s -> HTTP %s", kind, r.status_code)
            return ok
        except httpx.HTTPError as e:
            log.warning("webhook %s failed: %s", kind, type(e).__name__)
            return False

    def notify(self, alert: dict) -> None:
        self.post("alert", {"alert": {
            "id": alert["id"], "contract_id": alert["contract_id"], "contract_name": alert.get("contract_name", ""),
            "event_type": alert["event_type"], "severity": alert["severity"], "message": alert["message"],
            "due_date": alert["due_date"], "days_until": alert.get("days_until"), "label": alert.get("label"),
            "page": (alert.get("evidence") or {}).get("page")}})


class CompositeNotifier:
    def __init__(self, *parts):
        self.parts = parts

    def notify(self, alert: dict) -> None:
        for p in self.parts:
            try:
                p.notify(alert)
            except Exception as e:  # noqa: BLE001
                log.warning("notifier failed: %s", type(e).__name__)


def build_notifier():
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if not url:
        return LoggingNotifier()
    return CompositeNotifier(LoggingNotifier(), WebhookNotifier(url, os.environ.get("ALERT_WEBHOOK_SECRET", "")))


# ------------------------------------------------------------------ review items
def _state_path() -> Path:
    return Path(os.environ.get("SPA_NOTIFY_STATE") or config.ROOT / "data" / "review_notified.json")


def notify_new_review_items(items: list[dict], hook: WebhookNotifier | None = None) -> int:
    """Send each review item once (state file). items: [{contract_id, contract_name, field, status, confidence}]."""
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    hook = hook or (WebhookNotifier(url, os.environ.get("ALERT_WEBHOOK_SECRET", "")) if url else None)
    if hook is None:
        return 0
    p = _state_path()
    seen = set(json.loads(p.read_text())) if p.exists() else set()
    current = {f"{i['contract_id']}:{i['field']}" for i in items}
    sent = 0
    for it in items:
        key = f"{it['contract_id']}:{it['field']}"
        if key in seen:
            continue
        if hook.post("review_needed", {"review": {
                "contract_id": it["contract_id"], "contract_name": it.get("contract_name", ""), "field": it["field"],
                "status": it.get("status"), "confidence": it.get("confidence"), "page": it.get("source_page")}}):
            seen.add(key)
            sent += 1
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(seen & current | (seen - current))))     # keep history; resolved items stay "seen"
    return sent
