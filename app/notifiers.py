"""Outbound notifications: a signed webhook (Power Automate or any HTTPS endpoint) and/or direct email over SMTP.
Opt-in: nothing is sent unless ALERT_WEBHOOK_URL or SMTP_HOST + ALERT_EMAIL_TO is set.

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
        if kind in ("alert", "contract_ready", "review_needed") and "email" not in data:
            try:                                    # the finished, designed email: the flow only has to send it
                from .emailcards import build_email
                data = {**data, "email": build_email(kind, data)}
            except Exception as e:  # noqa: BLE001  (a design problem must never stop the plain event from being delivered)
                log.warning("email design failed: %s", type(e).__name__)
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



class EmailNotifier:
    """Sends the designed email straight over SMTP, so the product needs no Power Automate flow.

    ALERT_EMAIL_TO (comma-separated) and SMTP_HOST turn it on. SMTP_PORT (587), SMTP_USER, SMTP_PASSWORD, SMTP_FROM (defaults to
    SMTP_USER) and SMTP_SECURITY (starttls | ssl | none) are optional. Failures are logged by type and never raise."""
    smtp_factory = None                                  # tests inject a fake SMTP class

    def __init__(self, host: str, port: int, user: str, password: str, sender: str, recipients: list[str],
                 security: str = "starttls", timeout: float = 15.0):
        if not recipients:
            raise ValueError("ALERT_EMAIL_TO has no recipients.")
        self.host, self.port, self.user, self.password = host, port, user, password
        self.sender, self.recipients, self.security, self.timeout = sender, recipients, security, timeout

    def post(self, kind: str, data: dict) -> bool:
        if kind not in ("alert", "contract_ready", "review_needed"):
            return False
        import smtplib
        from email.message import EmailMessage
        from email.utils import formataddr
        try:
            from .emailcards import build_email
            mail = data.get("email") or build_email(kind, data)
            msg = EmailMessage()
            msg["Subject"], msg["To"] = mail["subject"], ", ".join(self.recipients)
            msg["From"] = formataddr((os.environ.get("EMAIL_SENDER_NAME", "SPA Intelligence"), self.sender))
            msg.set_content(mail["text"])
            msg.add_alternative(mail["html"], subtype="html")
            cls = self.smtp_factory or (smtplib.SMTP_SSL if self.security == "ssl" else smtplib.SMTP)
            with cls(self.host, self.port, timeout=self.timeout) as smtp:
                if self.security == "starttls":
                    smtp.starttls()
                if self.user:
                    smtp.login(self.user, self.password)
                smtp.send_message(msg)
            return True
        except Exception as e:  # noqa: BLE001  (never include the message: it can contain addresses or credentials)
            log.warning("email %s failed: %s", kind, type(e).__name__)
            return False

    def notify(self, alert: dict) -> None:
        self.post("alert", {"alert": {
            "id": alert["id"], "contract_id": alert["contract_id"], "contract_name": alert.get("contract_name", ""),
            "event_type": alert["event_type"], "severity": alert["severity"], "message": alert["message"],
            "due_date": alert["due_date"], "days_until": alert.get("days_until"), "label": alert.get("label"),
            "page": (alert.get("evidence") or {}).get("page")}})


class Hooks:
    """Every configured outbound channel (webhook, email) behind one post()."""

    def __init__(self, parts):
        self.parts = list(parts)

    def post(self, kind: str, data: dict) -> bool:
        results = [p.post(kind, data) for p in self.parts]
        return any(results)

    def notify(self, alert: dict) -> None:
        for p in self.parts:
            p.notify(alert)


def email_notifier_from_env() -> EmailNotifier | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    to = [a.strip() for a in os.environ.get("ALERT_EMAIL_TO", "").replace(";", ",").split(",") if a.strip()]
    if not host or not to:
        return None
    user = os.environ.get("SMTP_USER", "").strip()
    sec = (os.environ.get("SMTP_SECURITY") or "starttls").strip().lower()
    return EmailNotifier(host, int(os.environ.get("SMTP_PORT") or (465 if sec == "ssl" else 587)), user,
                         os.environ.get("SMTP_PASSWORD", ""), os.environ.get("SMTP_FROM", "").strip() or user, to,
                         sec if sec in ("starttls", "ssl", "none") else "starttls")


def configured_hook() -> Hooks | None:
    parts = []
    url = os.environ.get("ALERT_WEBHOOK_URL", "").strip()
    if url:
        parts.append(WebhookNotifier(url, os.environ.get("ALERT_WEBHOOK_SECRET", "")))
    em = email_notifier_from_env()
    if em:
        parts.append(em)
    return Hooks(parts) if parts else None


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
    hook = configured_hook()
    if hook is None:
        return LoggingNotifier()
    return CompositeNotifier(LoggingNotifier(), *hook.parts)


# ------------------------------------------------------------------ review items
def _state_path() -> Path:
    return Path(os.environ.get("SPA_NOTIFY_STATE") or config.ROOT / "data" / "review_notified.json")


def notify_new_review_items(items: list[dict], hook=None) -> int:
    """Send each review item once (state file). items: [{contract_id, contract_name, field, status, confidence}]."""
    hook = hook or configured_hook()
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


# ------------------------------------------------------------------ contract ready
def contract_summary(contract_id: str, name: str, c) -> dict:
    """Headline facts for a flow (e.g. add a row to an Excel table or a Teams post). No quotes, no contract text."""
    from .review import review_items
    return {"contract_id": contract_id, "contract_name": name, "unit_id": c.unit_id.value, "buyer": c.buyer.value,
            "currency": c.currency, "price": c.price.value, "handover_date": c.handover_date.value.isoformat() if c.handover_date.value else None,
            "jurisdiction": c.jurisdiction or (c.jurisdiction_detected.value if c.jurisdiction_detected else None),
            "milestones": len(c.payment_plan), "payment_plan_percent_sum": c.payment_plan_percent_sum,
            "plan": [{"name": m.name[:40], "percent": m.percent, "due_date": m.due_date.isoformat() if m.due_date else None}
                     for m in c.payment_plan[:10]],
            "warnings": len(c.warnings), "needs_review": len(review_items(c)), "model": c.model}


def notify_contract_ready(contract_id: str, name: str, c, hook=None) -> bool:
    hook = hook or configured_hook()
    return bool(hook and hook.post("contract_ready", {"contract": contract_summary(contract_id, name, c)}))
