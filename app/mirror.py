"""Durable copy of the app's files in PostgreSQL.

The app reads and writes ordinary files (PDFs, cached extractions, reviews, alerts). On a host with a disposable disk
those vanish on every restart. This module keeps a copy of them in the `app_files` table:

  * hydrate()  at startup: restore any file that is missing locally (the database is the memory of record).
  * flush()    after changes: upload files that are new or changed (compared by SHA-256).
  * start()    a background thread that flushes every few seconds, so a crash loses at most that interval.

Local files stay the working copy, so nothing else in the app had to change. It never deletes anything.
"""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from pathlib import Path
from typing import Callable

from app import db

log = logging.getLogger("spa.mirror")
MAX_FILE_BYTES = 30 * 1024 * 1024


class Mirror:
    def __init__(self, roots: dict[str, Path], file_kinds: tuple[str, ...] = ()):
        """roots: kind -> a directory (mirrored recursively); kinds in file_kinds are a single file path instead."""
        self.roots = {k: Path(v) for k, v in roots.items()}
        self.file_kinds = set(file_kinds)
        self._sha: dict[str, str] = {}              # logical path -> sha256 already in the database
        self._stat: dict[Path, tuple[int, int]] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.last_error: str | None = None
        self.last_flush: float | None = None
        self.on_change: Callable[[int], None] | None = None   # called with the number of files uploaded

    # ---- naming
    def _logical(self, kind: str, p: Path) -> str:
        root = self.roots[kind]
        return f"{kind}/{p.name}" if kind in self.file_kinds else f"{kind}/{p.relative_to(root).as_posix()}"

    def _local(self, logical: str) -> Path | None:
        kind, _, rel = logical.partition("/")
        root = self.roots.get(kind)
        if root is None or not rel or ".." in rel.split("/"):
            return None
        return root if kind in self.file_kinds else root / rel

    def _files(self):
        for kind, root in self.roots.items():
            if kind in self.file_kinds:
                if root.is_file():
                    yield kind, root
            elif root.is_dir():
                for p in root.rglob("*"):
                    if p.is_file() and not p.name.startswith(".") and p.suffix != ".tmp":
                        yield kind, p

    # ---- restore
    def hydrate(self) -> int:
        """Download every file that exists in the database but not on this disk. Returns the number restored."""
        restored = 0
        with db.connection() as cx:
            rows = cx.execute("select path, sha256 from app_files").fetchall()
            for path, sha in rows:
                self._sha[path] = sha
                dest = self._local(path)
                if dest is None or dest.exists():
                    continue
                row = cx.execute("select data from app_files where path = %s", (path,)).fetchone()
                if row is None:
                    continue
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".tmp")
                tmp.write_bytes(bytes(row[0]))
                tmp.replace(dest)
                restored += 1
        return restored

    # ---- save
    def flush(self) -> int:
        """Upload new or changed files. Returns how many were uploaded. Never raises."""
        with self._lock:
            try:
                pending = []
                for kind, p in self._files():
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    sig = (st.st_mtime_ns, st.st_size)
                    if self._stat.get(p) == sig or st.st_size > MAX_FILE_BYTES:
                        continue
                    pending.append((kind, p, sig))
                sent = 0
                if pending:
                    with db.connection() as cx:
                        for kind, p, sig in pending:
                            data = p.read_bytes()
                            sha = hashlib.sha256(data).hexdigest()
                            logical = self._logical(kind, p)
                            if self._sha.get(logical) != sha:
                                cx.execute(
                                    "insert into app_files (path, kind, data, size_bytes, sha256) values (%s,%s,%s,%s,%s) "
                                    "on conflict (path) do update set data = excluded.data, size_bytes = excluded.size_bytes, "
                                    "sha256 = excluded.sha256, kind = excluded.kind, updated_at = now()",
                                    (logical, kind, data, len(data), sha))
                                self._sha[logical] = sha
                                sent += 1
                            self._stat[p] = sig
                self.last_error, self.last_flush = None, time.time()
                if sent and self.on_change:
                    try:
                        self.on_change(sent)
                    except Exception as e:  # noqa: BLE001
                        log.warning("mirror on_change failed: %s", type(e).__name__)
                return sent
            except Exception as e:  # noqa: BLE001  (the app keeps working on local files)
                self.last_error = f"{type(e).__name__}: {str(e)[:160]}"
                log.warning("mirror flush failed: %s", self.last_error)
                return 0

    # ---- background loop
    def start(self, interval: float = 10.0) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop():
            while not self._stop.wait(interval):
                self.flush()
        self._thread = threading.Thread(target=loop, daemon=True, name="spa-mirror")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        self.flush()
