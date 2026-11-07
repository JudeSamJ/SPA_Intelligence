"""Human review of extracted fields. Decisions are stored per contract (append-only JSON) and applied as an
overlay when a contract is read: a human-corrected value overrides extraction and is flagged human_verified.
Verified/corrected contracts can be exported in the golden-set format (eval/golden/<doc_id>/{doc.pdf,labels.json})."""
from __future__ import annotations

import json
import re
import shutil
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from . import config
from .schema import ContractData, Grounding, Milestone, ReviewMark, Sourced

SCALARS = ["buyer", "unit_id", "price", "area_sqft", "handover_date", "grace_period_days", "delay_rate",
           "delay_basis", "delay_cap", "cancellation_clause"]
FIELD_RE = re.compile(r"^(payment_plan|ungrounded_rows)\.(\d{1,3})$")


class ReviewError(ValueError):
    pass


def _path(cid: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", cid):
        raise ReviewError("bad contract id")
    return config.REVIEW_DIR / f"{cid}.json"


def load_store(cid: str) -> dict:
    p = _path(cid)
    if p.exists():
        try:
            return json.loads(p.read_text())
        except ValueError:
            pass
    return {"decisions": [], "jurisdiction": None}


def save_store(cid: str, store: dict) -> None:
    config.REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    _path(cid).write_text(json.dumps(store, indent=2, default=str))


def store_mtime(cid: str) -> float:
    p = _path(cid)
    return p.stat().st_mtime if p.exists() else 0.0


def valid_field(field: str) -> bool:
    return field in SCALARS or bool(FIELD_RE.match(field))


def get_item(c: ContractData, field: str):
    if field in SCALARS:
        return getattr(c, field)
    m = FIELD_RE.match(field)
    if not m:
        raise ReviewError(f"unknown field '{field}'")
    rows = c.payment_plan if m[1] == "payment_plan" else c.ungrounded_rows
    i = int(m[2]) - 1
    if not 0 <= i < len(rows):
        raise ReviewError(f"no such row '{field}'")
    return rows[i]


def _coerce(field: str, value: Any):
    if field in ("buyer", "unit_id", "cancellation_clause"):
        v = str(value).strip()
        if not v:
            raise ReviewError("value must not be empty")
        return v
    if field == "handover_date":
        try:
            return date.fromisoformat(str(value))
        except ValueError:
            raise ReviewError("handover_date must be YYYY-MM-DD") from None
    if field == "delay_basis":
        if value not in ("percent_per_annum", "fixed_per_sqft_per_year", "other"):
            raise ReviewError("delay_basis must be percent_per_annum, fixed_per_sqft_per_year or other")
        return value
    try:
        v = float(value)
    except (TypeError, ValueError):
        raise ReviewError(f"{field} must be a number") from None
    if v < 0:
        raise ReviewError(f"{field} must be >= 0")
    return int(v) if field == "grace_period_days" else v


def add_decision(c: ContractData, cid: str, field: str, action: str, value: Any = None, note: str = "",
                 reviewer: str = "", source_page: int | None = None, source_quote: str | None = None) -> dict:
    """Validate against the (already overlaid) contract, then append. Raises ReviewError."""
    if not valid_field(field):
        raise ReviewError(f"unknown field '{field}'")
    if action not in ("accept", "correct", "reject"):
        raise ReviewError("action must be accept, correct or reject")
    get_item(c, field)                                     # row must exist
    d: dict[str, Any] = {"field": field, "action": action, "note": (note or "")[:500],
                         "reviewer": (reviewer or "anonymous")[:80],
                         "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if action == "correct":
        if FIELD_RE.match(field):
            if not isinstance(value, dict):
                raise ReviewError("a payment-plan row correction needs an object (name, percent, due_date, trigger)")
            row = {}
            if "percent" in value:
                pc = float(value["percent"])
                if not 0 <= pc <= 100:
                    raise ReviewError("percent must be between 0 and 100")
                row["percent"] = pc
            if "due_date" in value:
                row["due_date"] = None if value["due_date"] in (None, "") else date.fromisoformat(str(value["due_date"])).isoformat()
            for k in ("name", "trigger"):
                if k in value:
                    row[k] = str(value[k])[:200]
            d["value"] = row
        else:
            if value is None or value == "":
                raise ReviewError("a correction needs a value (use reject to mark it not stated)")
            v = _coerce(field, value)
            d["value"] = v.isoformat() if isinstance(v, date) else v
        if source_page:
            d["source_page"] = int(source_page)
        if source_quote:
            d["source_quote"] = source_quote[:1000]
    store = load_store(cid)
    store["decisions"].append(d)
    save_store(cid, store)
    return d


def apply_reviews(c: ContractData, store: dict, pdf_bytes: bytes | None = None) -> ContractData:
    """Overlay decisions in order (latest wins). Mutates and returns c."""
    from .evidence import locate
    for d in store.get("decisions", []):
        field = d["field"]
        try:
            item = get_item(c, field)
        except ReviewError:
            continue
        mark = ReviewMark(action=d["action"], note=d.get("note", ""), reviewer=d.get("reviewer", ""), at=d["at"])
        item.review, item.human_verified, item.needs_review = mark, True, False
        if d["action"] == "correct":
            v = d["value"]
            if isinstance(item, Sourced):
                item.value = date.fromisoformat(v) if field == "handover_date" else v
                if d.get("source_page"):
                    item.source_page = d["source_page"]
                if d.get("source_quote"):
                    item.source_quote = d["source_quote"]
                    if pdf_bytes:
                        item.evidence = locate(pdf_bytes, item.source_page, item.source_quote)
            else:
                for k, val in v.items():
                    setattr(item, k, date.fromisoformat(val) if k == "due_date" and val else val)
        elif d["action"] == "reject":
            if isinstance(item, Sourced):
                item.value = None
        item.confidence = 1.0
        item.grounding = Grounding(status="grounded" if d["action"] != "reject" else "not_stated",
                                   checks=[], claimed_value=None)
        if field.startswith("ungrounded_rows.") and d["action"] != "reject":
            if item not in c.payment_plan:
                c.payment_plan.append(item)
    # drop accepted rows from ungrounded list, recompute plan sum
    c.ungrounded_rows = [r for r in c.ungrounded_rows if r not in c.payment_plan]
    if c.payment_plan:
        c.payment_plan_percent_sum = round(sum(m.percent for m in c.payment_plan), 4)
    if store.get("jurisdiction"):
        c.jurisdiction = store["jurisdiction"]
    return c


def review_items(c: ContractData) -> list[dict]:
    out = []
    names = [(n, getattr(c, n)) for n in SCALARS]
    names += [(f"payment_plan.{i}", m) for i, m in enumerate(c.payment_plan, 1)]
    names += [(f"ungrounded_rows.{i}", m) for i, m in enumerate(c.ungrounded_rows, 1)]
    for name, it in names:
        if it.needs_review and not it.human_verified:
            g = it.grounding
            val = it.value if isinstance(it, Sourced) else {"name": it.name, "percent": it.percent,
                                                              "due_date": it.due_date, "trigger": it.trigger}
            out.append({"field": name, "value": val, "claimed_value": g.claimed_value if g else None,
                        "status": g.status if g else "ungrounded", "confidence": it.confidence,
                        "source_page": it.source_page, "source_quote": it.source_quote,
                        "reasons": [ch.detail for ch in (g.checks if g else []) if not ch.passed] or
                                   [ch.detail for ch in (g.checks if g else [])][:1]})
    return out


def label_value(it):
    if isinstance(it, Sourced):
        v = it.value
        return v.isoformat() if isinstance(v, date) else v
    return None


def export_golden(c: ContractData, cid: str, pdf_path: Path, out_root: Path, allow_partial: bool = False) -> Path:
    """Write eval/golden/<doc_id>/{doc.pdf, labels.json} from the effective (human-reviewed) contract."""
    pending = review_items(c)
    if pending and not allow_partial:
        raise ReviewError(f"{len(pending)} field(s) still need review: "
                          + ", ".join(p["field"] for p in pending) + ". Review them or pass allow_partial.")
    doc_id = re.sub(r"[^a-z0-9_]+", "_", Path(c.source_file or cid[:12]).stem.lower()).strip("_") or cid[:12]
    d = out_root / doc_id
    d.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(pdf_path, d / "doc.pdf")
    labels: dict[str, Any] = {"doc_id": doc_id, "kind": "reviewed", "synthetic": False,
                              "source": "exported from the review queue", "currency": c.currency}
    for n in SCALARS:
        it = getattr(c, n)
        labels[n] = {"value": label_value(it), "page": it.source_page, "quote": it.source_quote,
                     "human_verified": it.human_verified}
    labels["payment_plan"] = [{"name": m.name, "percent": m.percent,
                               "due_date": m.due_date.isoformat() if m.due_date else None, "trigger": m.trigger,
                               "page": m.source_page, "quote": m.source_quote, "human_verified": m.human_verified}
                              for m in c.payment_plan]
    labels["unverified_fields"] = [p["field"] for p in pending]
    (d / "labels.json").write_text(json.dumps(labels, indent=2, default=str))
    return d
