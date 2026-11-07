"""Wires the database into the running API: restore at startup, save in the background, keep the contracts table current.

With DATABASE_URL unset every function here is a no-op and the app runs on local files as before.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path

from app import config, db
from app.mirror import Mirror

log = logging.getLogger("spa.persistence")
_mirror: Mirror | None = None
_state = {"enabled": False, "ok": None, "restored": 0, "error": None}


def _roots() -> tuple[dict[str, Path], tuple[str, ...]]:
    from app.notifiers import _state_path
    roots = {"uploads": config.UPLOAD_DIR, "cache": config.CACHE_DIR, "reviews": config.REVIEW_DIR,
             "docsets": config.UPLOAD_DIR.parent / "docsets", "alerts": config.ALERTS_PATH, "notify": _state_path()}
    return roots, ("alerts", "notify")


def init() -> None:
    """Called once at startup. Never raises: if the database is unreachable the app runs on local files and says so in /api/health."""
    global _mirror
    _state.update(enabled=db.enabled(), ok=None, restored=0, error=None)
    if not db.enabled():
        return
    try:
        if os.environ.get("DB_AUTO_MIGRATE", "1") != "0":
            db.migrate()
        roots, file_kinds = _roots()
        _mirror = Mirror(roots, file_kinds)
        _mirror.on_change = lambda n: sync_contracts()
        _state["restored"] = _mirror.hydrate()
        _mirror.flush()                                   # push anything that exists locally but not yet in the database
        sync_contracts()
        _mirror.start(float(os.environ.get("DB_SYNC_SECONDS") or 10))
        _state["ok"] = True
        log.info("database connected (%s); restored %d files", db.describe(), _state["restored"])
    except Exception as e:  # noqa: BLE001
        _state.update(ok=False, error=f"{type(e).__name__}: {str(e)[:160]}")
        log.error("database unavailable, running on local files: %s", _state["error"])


def shutdown() -> None:
    if _mirror is not None:
        _mirror.stop()
    db.close()


def flush_soon() -> None:
    """Save changes now, without making the caller wait."""
    if _mirror is not None:
        threading.Thread(target=_mirror.flush, daemon=True, name="spa-flush").start()


def sync_contracts() -> None:
    """Refresh the readable `contracts` table from the registry. Best effort."""
    if not db.enabled():
        return
    from backend.api import deps
    from app.review import review_items
    rows = []
    for s in deps.list_sources():
        status, _ = deps.status_for(s)
        eff = deps.effective_contract(s) if status == "extracted" else None
        open_items = sum(1 for it in review_items(eff) if it.get("needs_review")) if eff else 0
        up = None
        meta = s.path.with_suffix(".meta.json")
        if s.kind == "upload" and meta.exists():
            import json
            up = json.loads(meta.read_text()).get("uploaded_at")
        rows.append((s.id, s.name, s.kind, s.pages, s.size, status, eff.model if eff else None,
                     eff.extracted_at if eff else None, open_items, up))
    try:
        with db.connection() as cx:
            for r in rows:
                cx.execute(
                    "insert into contracts (id, name, kind, pages, size_bytes, status, model, extracted_at, review_open, uploaded_at) "
                    "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) on conflict (id) do update set name = excluded.name, "
                    "pages = excluded.pages, size_bytes = excluded.size_bytes, status = excluded.status, model = excluded.model, "
                    "extracted_at = excluded.extracted_at, review_open = excluded.review_open, updated_at = now()", r)
    except Exception as e:  # noqa: BLE001
        log.warning("contracts sync failed: %s", type(e).__name__)


def status() -> dict:
    if not _state["enabled"]:
        return {"enabled": False}
    out = {"enabled": True, "ok": bool(_state["ok"]) and (_mirror.last_error is None if _mirror else False)}
    if _mirror and _mirror.last_flush:
        out["last_sync_age_s"] = int(__import__("time").time() - _mirror.last_flush)
    return out
