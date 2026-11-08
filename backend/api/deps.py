"""Shared state and helpers: contract registry, background jobs, rate limiting, error type."""
from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import Request

from app import config
from app.extract import extract_contract, file_hash, load_cached, pdf_stats
from app.schema import ContractData

ID_RE = re.compile(r"^[0-9a-f]{64}$")


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str):
        self.status, self.code, self.message = status, code, message


# ------------------------------------------------------------------ registry
@dataclass
class Source:
    id: str
    name: str
    kind: str          # "sample" | "upload"
    path: Path
    size: int
    pages: int
    scanned_suspect: bool


_hash_cache: dict[tuple[str, float, int], Source] = {}
_lock = threading.Lock()


def _display_name(path: Path, kind: str) -> str:
    if kind == "upload":
        meta = path.with_suffix(".meta.json")
        try:
            return json.loads(meta.read_text())["name"]
        except (OSError, ValueError, KeyError):
            pass
    return path.name


def _stable_id(path: Path, kind: str) -> str | None:
    """An upload that was OCR'd is stored as a different file (searchable copy) but keeps the id of what the user uploaded."""
    if kind != "upload":
        return None
    try:
        i = json.loads(path.with_suffix(".meta.json").read_text()).get("id")
    except (OSError, ValueError):
        return None
    return i if isinstance(i, str) and ID_RE.match(i) else None


def write_meta(path: Path, **updates) -> None:
    """Merge fields into an upload's .meta.json atomically."""
    mp = path.with_suffix(".meta.json")
    try:
        meta = json.loads(mp.read_text())
    except (OSError, ValueError):
        meta = {}
    meta.update(updates)
    tmp = mp.with_name(mp.name + ".tmp")
    tmp.write_text(json.dumps(meta))
    tmp.replace(mp)


def _scan(dirpath: Path, kind: str) -> list[Source]:
    out: list[Source] = []
    if not dirpath.exists():
        return out
    for p in sorted(dirpath.glob("*.pdf")):
        st = p.stat()
        key = (str(p), st.st_mtime, st.st_size)
        with _lock:
            src = _hash_cache.get(key)
        if src is None:
            data = p.read_bytes()
            stats = pdf_stats(data)
            src = Source(_stable_id(p, kind) or file_hash(data), _display_name(p, kind), kind, p, st.st_size,
                         stats["pages"], stats["scanned_suspect"])
            with _lock:
                _hash_cache[key] = src
        out.append(src)
    return out


def list_sources() -> list[Source]:
    return _scan(config.SAMPLES_DIR, "sample") + _scan(config.UPLOAD_DIR, "upload")


def get_source(contract_id: str) -> Source:
    if not ID_RE.match(contract_id):
        raise ApiError(404, "not_found", "Contract not found.")
    for s in list_sources():
        if s.id == contract_id:
            return s
    raise ApiError(404, "not_found", "Contract not found.")


_eff_cache: dict[tuple[str, float, float, str], ContractData] = {}


def effective_contract(src: Source) -> ContractData | None:
    """Cached extraction + grounding (re-run for old cache files, no LLM) + human review overlay."""
    from app.extract import pdf_pages
    from app.grounding import ground_contract
    from app.review import apply_reviews, load_store, store_mtime
    data = src.path.read_bytes()
    c = load_cached(data)
    if c is None:
        return None
    cp = extract_cache_path(src)
    key = (src.id, store_mtime(src.id), cp.stat().st_mtime if cp.exists() else 0.0, config.model_tag())
    hit = _eff_cache.get(key)
    if hit is None:
        if c.grounded_version is None:                      # extraction predates grounding
            ground_contract(c, data, pdf_pages(data))
        hit = apply_reviews(c, load_store(src.id), data)
        if len(_eff_cache) > 64:
            _eff_cache.clear()
        _eff_cache[key] = hit
    return hit.model_copy(deep=True)


def extract_cache_path(src: Source) -> Path:
    from app.extract import cache_path
    return cache_path(src.id)


def get_contract(contract_id: str) -> tuple[Source, ContractData]:
    src = get_source(contract_id)
    c = effective_contract(src)
    if c is None:
        raise ApiError(409, "not_extracted", "This contract has not been extracted yet.")
    return src, c


# ------------------------------------------------------------------ jobs
@dataclass
class Job:
    state: str = "queued"            # queued | running | done | error
    error: str | None = None
    updated: float = field(default_factory=time.time)


JOBS: dict[str, Job] = {}


def start_extraction(src: Source, force: bool) -> Job:
    with _lock:
        existing = JOBS.get(src.id)
        if existing and existing.state in ("queued", "running", "ocr"):
            return existing
        job = JOBS[src.id] = Job()

    def run():
        job.state = "running"
        try:
            data = src.path.read_bytes()
            from app import ocr
            if src.kind == "upload" and ocr.pages_needing_ocr(data) and ocr.enabled():
                job.state = "ocr"                              # scanned pages: read them first, then extract as usual
                data = _ocr_in_place(src, data)
                job.state = "running"
            extract_contract(data, source_name=src.name, use_cache=not force)
            job.state = "done"
            from backend.api.routes.obligations import recompute_now
            try:
                from app.notifiers import notify_contract_ready
                eff = effective_contract(src)
                if eff is not None:
                    notify_contract_ready(src.id, src.name, eff)      # opt-in webhook; never raises into the job
            except Exception:  # noqa: BLE001
                pass
            recompute_now()                       # contract changed -> refresh the alert feed
            from backend.api import persistence
            persistence.flush_soon()              # save the new extraction to the database now
        except Exception as e:  # noqa: BLE001  (surface a safe message; never contract text)
            job.state, job.error = "error", f"{type(e).__name__}: {str(e)[:300]}"
        job.updated = time.time()

    threading.Thread(target=run, daemon=True, name=f"extract-{src.id[:8]}").start()
    return job


def _ocr_in_place(src: Source, data: bytes) -> bytes:
    """Make the upload searchable. The user's original is kept untouched under originals/; the working copy keeps the same contract id."""
    from app import ocr
    searchable, report = ocr.make_searchable(data)
    orig_dir = src.path.parent / "originals"
    orig_dir.mkdir(exist_ok=True)
    keep = orig_dir / f"{src.id}.pdf"
    if not keep.exists():
        keep.write_bytes(data)
    write_meta(src.path, id=src.id, ocr={"engine": report["engine"], "verifier": report["verifier"],
                                         "pages": sorted(int(p) for p in report["pages"]), "unread": report["unread"],
                                         "original_sha256": file_hash(data)})
    tmp = src.path.with_name(src.path.name + ".tmp")
    tmp.write_bytes(searchable)
    tmp.replace(src.path)                                       # atomic: a reader sees the old file or the new one, never half
    return searchable


def status_for(src: Source) -> tuple[str, str | None]:
    job = JOBS.get(src.id)
    if job and job.state in ("queued", "running", "ocr"):
        return job.state, None
    if load_cached(src.path.read_bytes()) is not None:
        return "extracted", None
    if job and job.state == "error":
        return "error", job.error
    return "not_extracted", None


# ------------------------------------------------------------------ rate limit
class RateLimiter:
    """In-memory sliding window per client IP (single-process; fine for a demo)."""

    def __init__(self, limit: int, window: int, name: str):
        self.limit, self.window, self.name = limit, window, name
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def __call__(self, request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        now = time.monotonic()
        with self.lock:
            q = self.hits[ip]
            while q and now - q[0] > self.window:
                q.popleft()
            if len(q) >= self.limit:
                raise ApiError(429, "rate_limited", f"Too many {self.name} requests; please wait a moment.")
            q.append(now)


upload_limiter = RateLimiter(*config.UPLOAD_RATE, "upload")
chat_limiter = RateLimiter(*config.CHAT_RATE, "chat")


def sanitize_filename(name: str) -> str:
    base = Path(name or "contract.pdf").name
    base = re.sub(r"[^\w.\- ()]", "_", base)[:120].strip() or "contract.pdf"
    return base if base.lower().endswith(".pdf") else base + ".pdf"


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
