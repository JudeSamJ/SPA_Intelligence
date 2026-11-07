"""D365 F&O export: map a contract's payment schedule and statute/penalty exposure into AR / cash-flow rows.

Default is DRY RUN: build rows, validate them against erp/d365_mapping.yaml, return JSON + CSV for download.
A live OData push is only possible when ERP_PUSH_ENABLED=1 and tenant/app credentials are in the environment; it
needs an explicit confirm flag, refuses placeholder (TODO_) names, and writes an audit-log line per push.
Entity and field names in the mapping file are PLACEHOLDERS the user must confirm. No live calls happen in tests.
"""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

import httpx
import yaml

from .. import config
from ..schema import ContractData
from ..statute_gap import compute_gap, effective_jurisdiction
from ..penalty import SimulationUnavailable, penalty_for_contract

MAPPING_PATH = config.ROOT / "erp" / "d365_mapping.yaml"
AUDIT_PATH_ENV = "SPA_AUDIT_DIR"


class PushError(RuntimeError):
    pass


def mapping() -> dict:
    return yaml.safe_load(MAPPING_PATH.read_text(encoding="utf-8"))


def audit_dir() -> Path:
    return Path(os.environ.get(AUDIT_PATH_ENV) or config.ROOT / "data" / "audit")


def build_rows(c: ContractData, contract_id: str, name: str, delay_days: int | None, as_of: date,
               amounts_paid: list[dict] | None = None) -> list[dict]:
    """Source rows (our keys). Payment lines from the plan; exposure lines for the chosen delay scenario."""
    cur = c.currency or config.load_rules().get("currency", "")
    ref = c.unit_id.value or name
    rows = []
    for i, m in enumerate(c.payment_plan, 1):
        amt = round(c.price.value * m.percent / 100, 2) if c.price.value is not None else None
        rows.append({"contract_ref": ref, "line_type": "payment", "description": m.name, "due_date": m.due_date,
                     "amount": amt, "currency": cur, "evidence_page": m.source_page})
    if delay_days is not None:
        try:
            pen = penalty_for_contract(c, delay_days)
            rows.append({"contract_ref": ref, "line_type": "exposure", "description": f"Contractual delay compensation, {delay_days} days",
                         "due_date": as_of, "amount": pen["penalty"], "currency": cur, "evidence_page": c.delay_rate.source_page})
        except SimulationUnavailable:
            pass
        g = compute_gap(c, delay_days, as_of, amounts_paid, pack_id=effective_jurisdiction(c))
        if g["can_compute"]:
            rows.append({"contract_ref": ref, "line_type": "exposure", "description": f"Statutory delay interest, {delay_days} days (unreviewed legal logic)",
                         "due_date": as_of, "amount": g["statutory"]["amount"], "currency": cur,
                         "evidence_page": c.handover_date.source_page})
    return rows


def validate(rows: list[dict], m: dict | None = None) -> tuple[list[dict], list[dict]]:
    """(payload rows keyed by TARGET names, errors). Errors never include contract text beyond the row index/field."""
    m = m or mapping()
    out, errors = [], []
    for i, r in enumerate(rows, 1):
        p = {}
        for f in m["fields"]:
            v = r.get(f["source"])
            where = {"row": i, "field": f["target"], "source": f["source"]}
            if v is None or v == "":
                if f.get("required"):
                    errors.append({**where, "error": "required value is missing"})
                p[f["target"]] = None
                continue
            try:
                if f["type"] == "date":
                    v = v.isoformat() if isinstance(v, (date, datetime)) else date.fromisoformat(str(v)).isoformat()
                elif f["type"] == "decimal":
                    d = Decimal(str(v))
                    if d < 0:
                        raise ValueError("must be >= 0")
                    v = float(d.quantize(Decimal("0.01")))
                elif f["type"] == "integer":
                    v = int(v)
                else:
                    v = str(v)
                    if len(v) > f.get("max_len", 10_000):
                        errors.append({**where, "error": f"longer than {f['max_len']} characters"})
            except (ValueError, InvalidOperation):
                errors.append({**where, "error": f"not a valid {f['type']}"})
                v = None
            p[f["target"]] = v
        out.append(p)
    return out, errors


def to_csv(payload: list[dict], m: dict | None = None) -> str:
    m = m or mapping()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=[f["target"] for f in m["fields"]])
    w.writeheader()
    w.writerows(payload)
    return buf.getvalue()


def export(c: ContractData, contract_id: str, name: str, delay_days: int | None, as_of: date, amounts_paid=None) -> dict:
    m = mapping()
    rows = build_rows(c, contract_id, name, delay_days, as_of, amounts_paid)
    payload, errors = validate(rows, m)
    return {"mode": "dry_run", "entity": m["entities"]["schedule_lines"], "placeholder_mapping": bool(m.get("placeholder")),
            "mapping_note": "Entity and field names are PLACEHOLDERS: confirm them in your D365 environment (erp/d365_mapping.yaml).",
            "rows": payload, "row_count": len(payload), "errors": errors, "valid": not errors,
            "csv": to_csv(payload, m), "push_enabled": push_enabled(), "disclaimer": config.DISCLAIMER}


# ------------------------------------------------------------------ live push (gated)
def push_enabled() -> bool:
    return os.environ.get("ERP_PUSH_ENABLED") == "1"


class D365Client:
    transport: httpx.BaseTransport | None = None      # tests inject a mock transport; never a live call in tests

    def __init__(self):
        need = ["D365_TENANT_ID", "D365_CLIENT_ID", "D365_CLIENT_SECRET", "D365_RESOURCE"]
        missing = [v for v in need if not os.environ.get(v)]
        if missing:
            raise PushError("Missing environment variables: " + ", ".join(missing))
        self.tenant, self.cid, self.secret = os.environ["D365_TENANT_ID"], os.environ["D365_CLIENT_ID"], os.environ["D365_CLIENT_SECRET"]
        self.resource = os.environ["D365_RESOURCE"].rstrip("/")

    def token(self, c: httpx.Client) -> str:
        r = c.post(f"https://login.microsoftonline.com/{self.tenant}/oauth2/v2.0/token",
                   data={"grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret,
                         "scope": f"{self.resource}/.default"})
        if r.status_code != 200:
            raise PushError(f"Token request failed (HTTP {r.status_code}).")
        return r.json()["access_token"]

    def push(self, entity: str, rows: list[dict]) -> list[dict]:
        results = []
        with httpx.Client(timeout=30, transport=self.transport) as c:
            h = {"Authorization": f"Bearer {self.token(c)}", "Content-Type": "application/json"}
            for i, row in enumerate(rows, 1):
                r = c.post(f"{self.resource}/data/{entity}", headers=h, content=json.dumps(row))
                results.append({"row": i, "status": r.status_code, "ok": r.status_code in (200, 201, 204)})
        return results


def audit(entry: dict) -> None:
    d = audit_dir()
    d.mkdir(parents=True, exist_ok=True)
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), **entry}
    with open(d / "erp_push.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line) + "\n")


def push(c: ContractData, contract_id: str, name: str, delay_days: int | None, as_of: date, confirm: bool,
         reviewer: str = "", amounts_paid=None, client_cls=D365Client) -> dict:
    if not push_enabled():
        raise PushError("Live push is disabled. Set ERP_PUSH_ENABLED=1 (and the D365_* credentials) to enable it.")
    if not confirm:
        raise PushError("Push needs explicit confirmation (confirm=true).")
    m = mapping()
    if any(str(f["target"]).startswith("TODO_") for f in m["fields"]) or str(m["entities"]["schedule_lines"]).startswith("TODO_"):
        raise PushError("The mapping still contains placeholder (TODO_) names. Confirm them in erp/d365_mapping.yaml first.")
    rows = build_rows(c, contract_id, name, delay_days, as_of, amounts_paid)
    payload, errors = validate(rows, m)
    if errors:
        raise PushError(f"{len(errors)} validation error(s); fix them before pushing.")
    try:
        res = client_cls().push(m["entities"]["schedule_lines"], payload)
    except PushError as e:
        audit({"contract_id": contract_id, "reviewer": reviewer or "anonymous", "rows": len(payload), "result": "error", "error": str(e)[:200]})
        raise
    audit({"contract_id": contract_id, "reviewer": reviewer or "anonymous", "rows": len(payload), "entity": m["entities"]["schedule_lines"],
           "result": "ok" if all(r["ok"] for r in res) else "partial", "statuses": [r["status"] for r in res]})
    return {"pushed": sum(r["ok"] for r in res), "rows": len(payload), "results": res}
