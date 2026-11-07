"""Database tests. They run against a REAL PostgreSQL (the same engine Supabase uses), never a mock of SQL.

Point them at a throwaway database with TEST_DATABASE_URL (default: a local server on 127.0.0.1:54329). They skip when no
server is reachable, and they refuse to drop tables on any non-local host, so they can never touch a real Supabase project.
"""
import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse

import psycopg
import pytest
from fastapi.testclient import TestClient

from app import config, db
from app.mirror import Mirror
from backend.api import deps, persistence
from backend.api.main import create_app
from backend.tests.test_api import SAMPLES, blank_pdf, env, sid  # noqa: F401  (env fixture)

TEST_URL = os.environ.get("TEST_DATABASE_URL") or "postgresql://postgres@127.0.0.1:54329/postgres"


def _reachable() -> bool:
    try:
        psycopg.connect(TEST_URL, connect_timeout=2).close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _reachable(), reason="no test PostgreSQL reachable (set TEST_DATABASE_URL)")


@pytest.fixture(autouse=True)
def fast_pool_timeout(monkeypatch):
    monkeypatch.setenv("DB_POOL_TIMEOUT", "1")


@pytest.fixture
def pg(monkeypatch):
    host = urlparse(TEST_URL).hostname
    assert host in ("127.0.0.1", "localhost", "::1") or os.environ.get("TEST_DB_ALLOW_DROP") == "1", \
        "refusing to drop tables on a non-local database"
    monkeypatch.setenv("DATABASE_URL", TEST_URL)
    db.close()
    with psycopg.connect(TEST_URL, autocommit=True) as cx:
        for t in ("audit_log", "buyer_assignments", "contracts", "app_files"):
            cx.execute(f"drop table if exists public.{t} cascade")
    yield TEST_URL
    persistence.shutdown()


def q(sql, args=()):
    with psycopg.connect(TEST_URL, autocommit=True) as cx:
        cur = cx.execute(sql, args)
        return cur.fetchall() if cur.description else []


# ------------------------------------------------------------------ schema
def test_migrate_is_idempotent_and_rls_is_on(pg):
    db.migrate()
    db.migrate()                                                    # second run changes nothing and does not fail
    h = db.health()
    assert h["ok"] and h["missing"] == [] and h["rls_on"] is True
    assert set(h["tables"]) == set(db.TABLES)
    assert "password" not in str(h).lower()


def test_anon_role_sees_nothing(pg):
    """Supabase's public REST API uses the anon role. With RLS on and no policy it must read zero rows."""
    db.migrate()
    q("insert into contracts (id, name, kind) values (%s, 'x', 'upload')", ("a" * 64,))
    with psycopg.connect(TEST_URL, autocommit=True) as cx:
        cx.execute("drop role if exists anon_t")
        cx.execute("create role anon_t nologin")
        cx.execute("grant usage on schema public to anon_t")
        cx.execute("grant select, insert on all tables in schema public to anon_t")
        cx.execute("set role anon_t")
        assert cx.execute("select count(*) from contracts").fetchone()[0] == 0
        with pytest.raises(psycopg.errors.InsufficientPrivilege):   # insert violates the (absent) policy
            cx.execute("insert into contracts (id, name, kind) values (%s, 'y', 'upload')", ("b" * 64,))
        cx.execute("reset role")
        cx.execute("drop owned by anon_t")
        cx.execute("drop role anon_t")


def test_contract_id_must_be_a_sha256(pg):
    db.migrate()
    with pytest.raises(psycopg.errors.CheckViolation):
        q("insert into contracts (id, name, kind) values ('nope', 'x', 'upload')")


def test_health_reports_unreachable_without_raising(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://postgres:secret@127.0.0.1:1/none")
    db.close()
    h = db.health()
    assert h["enabled"] and h["ok"] is False and "secret" not in str(h)
    db.close()


def test_ssl_is_required_for_remote_hosts_only():
    assert db._with_ssl("postgresql://u:p@db.x.supabase.co:5432/postgres").endswith("sslmode=require")
    assert "sslmode" not in db._with_ssl("postgresql://u:p@127.0.0.1:5432/postgres")
    assert db._with_ssl("postgresql://u:p@h/db?sslmode=disable").count("sslmode") == 1


# ------------------------------------------------------------------ mirror
def make_mirror(tmp_path):
    roots = {"uploads": tmp_path / "uploads", "cache": tmp_path / "cache", "alerts": tmp_path / "alerts.json"}
    return Mirror(roots, ("alerts",))


def test_flush_then_hydrate_restores_identical_bytes(pg, tmp_path):
    db.migrate()
    a = make_mirror(tmp_path / "a")
    (tmp_path / "a" / "uploads").mkdir(parents=True)
    (tmp_path / "a" / "cache").mkdir()
    pdf = (SAMPLES / "sample_a.pdf").read_bytes() if (SAMPLES / "sample_a.pdf").exists() else blank_pdf("hello")
    (tmp_path / "a" / "uploads" / "x.pdf").write_bytes(pdf)
    (tmp_path / "a" / "cache" / "deep" / "y.json").parent.mkdir()
    (tmp_path / "a" / "cache" / "deep" / "y.json").write_text('{"k": 1}')
    (tmp_path / "a" / "alerts.json").write_text("[1,2]")
    assert a.flush() == 3

    b = make_mirror(tmp_path / "b")                                  # a fresh, empty disk (a Render restart)
    assert b.hydrate() == 3
    assert (tmp_path / "b" / "uploads" / "x.pdf").read_bytes() == pdf
    assert (tmp_path / "b" / "cache" / "deep" / "y.json").read_text() == '{"k": 1}'
    assert (tmp_path / "b" / "alerts.json").read_text() == "[1,2]"


def test_flush_uploads_only_changes(pg, tmp_path):
    db.migrate()
    m = make_mirror(tmp_path)
    (tmp_path / "cache").mkdir()
    f = tmp_path / "cache" / "e.json"
    f.write_text("one")
    assert m.flush() == 1
    assert m.flush() == 0                                            # nothing changed
    f.write_text("two!")
    assert m.flush() == 1
    assert bytes(q("select data from app_files where path = 'cache/e.json'")[0][0]) == b"two!"
    f.write_text("two!")                                             # same bytes again: touched but not changed
    os.utime(f, (1, 1))
    assert m.flush() == 0


def test_hydrate_never_overwrites_and_ignores_bad_paths(pg, tmp_path):
    db.migrate()
    m = make_mirror(tmp_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "keep.json").write_text("local")
    sha = hashlib.sha256(b"db").hexdigest()
    for path in ("cache/keep.json", "cache/../escape.txt", "weird/zzz.json", "uploads/"):
        q("insert into app_files (path, kind, data, size_bytes, sha256) values (%s,'x',%s,2,%s)", (path, b"db", sha))
    m.hydrate()
    assert (tmp_path / "cache" / "keep.json").read_text() == "local"   # existing local file wins
    assert not (tmp_path / "escape.txt").exists()                       # path traversal ignored
    assert not (tmp_path / "weird").exists()                            # unknown kind ignored


def test_flush_never_raises_when_the_database_is_down(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none")
    db.close()
    m = make_mirror(tmp_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "e.json").write_text("x")
    assert m.flush() == 0 and m.last_error
    db.close()


def test_oversized_files_are_skipped(pg, tmp_path, monkeypatch):
    db.migrate()
    monkeypatch.setattr("app.mirror.MAX_FILE_BYTES", 5)
    m = make_mirror(tmp_path)
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "big.json").write_text("0123456789")
    assert m.flush() == 0


# ------------------------------------------------------------------ the running app
@pytest.fixture
def app_env(env, pg, monkeypatch):
    monkeypatch.setenv("SPA_NOTIFY_STATE", str(env / "notified.json"))
    return env


def test_upload_survives_a_restart_with_a_wiped_disk(app_env):
    pdf = blank_pdf("Sale and Purchase Agreement. " * 20)
    cid = hashlib.sha256(pdf).hexdigest()
    with TestClient(create_app()) as c:
        r = c.post("/api/contracts/upload?extract=false", files={"file": ("my spa.pdf", pdf, "application/pdf")})
        assert r.status_code == 202
        persistence._mirror.flush()                                  # what the background loop does every few seconds
        assert c.get("/api/health").json()["database"]["ok"] is True
    # the container restarts and its disk is empty
    import shutil
    shutil.rmtree(config.UPLOAD_DIR)
    deps._hash_cache.clear()
    with TestClient(create_app()) as c2:
        ids = {x["id"]: x for x in c2.get("/api/contracts").json()}
        assert cid in ids and ids[cid]["name"] == "my spa.pdf"        # the original file name came back too
        assert c2.get(f"/api/contracts/{cid}/pdf").content == pdf
    row = q("select name, kind, status, pages from contracts where id = %s", (cid,))
    assert row and row[0][1] == "upload" and row[0][2] == "not_extracted" and row[0][3] == 1


def test_app_still_works_when_the_database_is_unreachable(env, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/none")
    monkeypatch.setenv("SPA_NOTIFY_STATE", str(env / "notified.json"))
    db.close()
    with TestClient(create_app()) as c:
        h = c.get("/api/health").json()
        assert h["status"] == "ok" and h["database"]["enabled"] is True and h["database"]["ok"] is False
        assert c.get("/api/contracts").status_code == 200
    persistence.shutdown()


def test_health_is_unchanged_without_a_database(env, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with TestClient(create_app()) as c:
        assert c.get("/api/health").json()["database"] == {"enabled": False}
