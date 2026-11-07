"""PostgreSQL / Supabase access. One setting turns it on: DATABASE_URL (the connection string from Supabase).

Everything here is optional: with DATABASE_URL unset the app keeps working on local files, exactly as before.
The connection string is a secret. It is read from the environment only, never logged and never sent to a browser.
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from app import config

log = logging.getLogger("spa.db")
SCHEMA_PATH = config.ROOT / "supabase" / "schema.sql"
_pool = None
_pool_url = None
_lock = threading.Lock()


def url() -> str:
    return (os.environ.get("DATABASE_URL") or "").strip()


def enabled() -> bool:
    return bool(url())


def _with_ssl(u: str) -> str:
    """Supabase requires TLS. Add sslmode=require for any non-local host that did not choose a mode itself."""
    p = urlparse(u)
    if (p.hostname or "") in ("localhost", "127.0.0.1", "::1", "") or "sslmode" in parse_qs(p.query):
        return u
    return u + ("&" if p.query else "?") + "sslmode=require"


def describe() -> str:
    """Host and database only. Never the user or password."""
    p = urlparse(url())
    return f"{p.hostname or '?'}:{p.port or 5432}{p.path or ''}" if p.hostname else "(not set)"


def _get_pool():
    global _pool, _pool_url
    u = url()
    with _lock:
        if _pool is not None and _pool_url == u:
            return _pool
        if _pool is not None:
            _pool.close()
        from psycopg_pool import ConnectionPool
        _pool = ConnectionPool(_with_ssl(u), min_size=0, max_size=4, open=True, timeout=float(os.environ.get("DB_POOL_TIMEOUT") or 15),
                               kwargs={"autocommit": True, "connect_timeout": 10, "prepare_threshold": None},
                               check=ConnectionPool.check_connection, name="spa-db")
        _pool_url = u
        return _pool


def connection():
    """Context manager yielding a pooled autocommit connection."""
    if not enabled():
        raise RuntimeError("DATABASE_URL is not set")
    return _get_pool().connection()


def close() -> None:
    global _pool, _pool_url
    with _lock:
        if _pool is not None:
            _pool.close()
        _pool, _pool_url = None, None


def migrate() -> None:
    """Create the tables if they are missing. Idempotent."""
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with connection() as cx:
        cx.execute(sql)


TABLES = ("app_files", "contracts", "buyer_assignments", "audit_log")


def health() -> dict:
    """Connection status for /api/health and the check script. Never includes credentials."""
    if not enabled():
        return {"enabled": False}
    try:
        with connection() as cx:
            ver = cx.execute("select current_setting('server_version')").fetchone()[0]
            have = {r[0] for r in cx.execute(
                "select tablename from pg_tables where schemaname = 'public' and tablename = any(%s)", (list(TABLES),))}
            rls = {r[0]: r[1] for r in cx.execute(
                "select relname, relrowsecurity from pg_class where relnamespace = 'public'::regnamespace "
                "and relname = any(%s)", (list(TABLES),))}
        return {"enabled": True, "ok": True, "server": ver, "host": describe(),
                "tables": sorted(have), "missing": [t for t in TABLES if t not in have],
                "rls_on": all(rls.get(t) for t in have)}
    except Exception as e:  # noqa: BLE001
        return {"enabled": True, "ok": False, "host": describe(), "error": f"{type(e).__name__}: {str(e)[:160]}"}
