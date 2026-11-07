"""Check the database connection end to end. Prints PASS/FAIL per step. Never prints the password.

    DATABASE_URL='postgresql://...' python scripts/check_supabase.py          (or put DATABASE_URL in .env)
    python scripts/check_supabase.py --no-migrate                              (do not create tables)

It creates the tables if missing, writes one throwaway row, reads it back, deletes it, and confirms Row Level Security is on.
"""
from __future__ import annotations

import socket
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import db  # noqa: E402

results: list[tuple[str, bool, str]] = []


def step(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, ok, detail))
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    return ok


def main() -> int:
    migrate = "--no-migrate" not in sys.argv
    if not step("DATABASE_URL is set", db.enabled(), "" if db.enabled() else "set it in the environment or .env"):
        return 1
    host = db.describe().split(":")[0]
    print(f"      target: {db.describe()}")
    try:
        v4 = bool(socket.getaddrinfo(host, None, socket.AF_INET))
    except OSError:
        v4 = False
    if host.startswith("db.") and host.endswith(".supabase.co") and not v4:
        print("      note: this direct host is IPv6-only. Render and many networks are IPv4-only: use the\n"
              "            'Session pooler' string from Supabase (Connect > Session pooler) instead.")
    h = db.health()
    if not step("connect and query", bool(h.get("ok")), h.get("server") and f"PostgreSQL {h['server']}" or h.get("error", "")):
        return 1
    if migrate:
        try:
            db.migrate()
            step("create tables (idempotent)", True)
        except Exception as e:  # noqa: BLE001
            step("create tables (idempotent)", False, f"{type(e).__name__}: {str(e)[:120]}")
            return 1
    h = db.health()
    step("all tables exist", not h["missing"], ", ".join(h["missing"]) or f"{len(h['tables'])} tables")
    step("Row Level Security on for every table", bool(h.get("rls_on")),
         "" if h.get("rls_on") else "run supabase/schema.sql again")
    key = f"selftest/{uuid.uuid4().hex}"
    try:
        with db.connection() as cx:
            cx.execute("insert into app_files (path, kind, data, size_bytes, sha256) values (%s,'selftest',%s,4,'x')",
                       (key, b"ping"))
            got = cx.execute("select data from app_files where path = %s", (key,)).fetchone()
            cx.execute("delete from app_files where path = %s", (key,))
            gone = cx.execute("select count(*) from app_files where path = %s", (key,)).fetchone()[0] == 0
        step("write, read back, delete a test row", bool(got) and bytes(got[0]) == b"ping" and gone)
    except Exception as e:  # noqa: BLE001
        step("write, read back, delete a test row", False, f"{type(e).__name__}: {str(e)[:120]}")
    bad = [n for n, ok, _ in results if not ok]
    print("\nAll checks passed." if not bad else f"\n{len(bad)} check(s) failed.")
    db.close()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
