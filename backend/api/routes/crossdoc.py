"""Cross-document sets: list, analyse, create and add documents (PDF / CSV / XLSX)."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Query, UploadFile
from pydantic import BaseModel, Field

from app import config, crossdoc as cd
from app.extract import file_hash
from backend.api import deps
from backend.api.deps import ApiError

router = APIRouter(prefix="/crossdoc", tags=["crossdoc"])
SAMPLE_DIR = config.ROOT / "samples" / "crossdoc"


def docsets_dir() -> Path:
    return config.UPLOAD_DIR.parent / "docsets"


def _dirs() -> list[tuple[str, Path]]:
    out = []
    for base, kind in ((SAMPLE_DIR, "sample"), (docsets_dir(), "user")):
        if base.exists():
            out += [(kind, d) for d in sorted(base.iterdir()) if (d / "manifest.json").exists()]
    return out


def _find(set_id: str) -> tuple[str, Path]:
    if not re.fullmatch(r"[a-z0-9_]{1,40}", set_id or ""):
        raise ApiError(404, "not_found", "No such document set.")
    for kind, d in _dirs():
        if d.name == set_id:
            return kind, d
    raise ApiError(404, "not_found", "No such document set.")


def _spa_contract(d: Path, mf: dict):
    cid = mf.get("spa_contract_id")
    if not cid and (d / "spa.pdf").exists():
        cid = file_hash((d / "spa.pdf").read_bytes())
    if not cid:
        return None
    try:
        src = deps.get_source(cid)
    except ApiError:
        return None
    return deps.effective_contract(src)


@router.get("/sets")
def list_sets():
    out = []
    for kind, d in _dirs():
        mf = json.loads((d / "manifest.json").read_text())
        out.append({"set_id": d.name, "kind": kind, "unit_key": mf["unit_key"], "documents": [x["type"] for x in mf["documents"]],
                    "synthetic": kind == "sample", "planted": len(mf.get("planted", [])) if kind == "sample" else None})
    return {"sets": out}


@router.get("/sets/{set_id}")
def analyse(set_id: str, extract: bool = Query(False, description="Allow LLM calls to read uncached brochure/filing PDFs.")):
    kind, d = _find(set_id)
    mf = json.loads((d / "manifest.json").read_text())
    ds = cd.load_set(d)
    spa = _spa_contract(d, mf)
    llm_calls = 0

    def facts(doc):
        nonlocal llm_calls
        pdf = Path(doc.path).read_bytes()
        hit = cd.load_facts_cached(pdf)
        if hit or not extract:
            return hit
        if not config.llm_configured():
            raise ApiError(503, "llm_not_configured", config.setup_hint())
        llm_calls += 1
        return cd.extract_facts_cached(pdf)

    res = cd.analyze(ds, spa, facts)
    res.update({"kind": kind, "synthetic": kind == "sample", "llm_calls_made": llm_calls,
                "planted": mf.get("planted") if kind == "sample" else None})
    if kind == "sample" and mf.get("planted") is not None and not res["pending"]:
        res["planted_score"] = cd.score_planted(res["conflicts"], mf["planted"])
    if res["pending"]:
        res["pending_note"] = ("Some documents have not been read yet. Repeat with extract=true to read them "
                               "(one LLM call per PDF); results are cached.")
    return res


class NewSet(BaseModel):
    unit_key: str = Field(..., min_length=1, max_length=60)
    spa_contract_id: Optional[str] = Field(None, pattern=r"^[0-9a-f]{64}$")
    currency: Optional[str] = Field(None, max_length=3)


@router.post("/sets", status_code=201)
def create_set(body: NewSet):
    set_id = "u_" + re.sub(r"[^a-z0-9]", "", cd.unit_key(body.unit_key))[:24]
    d = docsets_dir() / set_id
    if (d / "manifest.json").exists():
        raise ApiError(409, "exists", "A set for this unit already exists.")
    d.mkdir(parents=True, exist_ok=True)
    docs = [{"type": "spa", "file": "spa.pdf"}] if body.spa_contract_id else []
    (d / "manifest.json").write_text(json.dumps({"set_id": set_id, "unit_key": body.unit_key, "currency": body.currency,
                                                 "spa_contract_id": body.spa_contract_id, "documents": docs}))
    return {"set_id": set_id}


@router.post("/sets/{set_id}/documents", status_code=201)
async def add_document(set_id: str, doc_type: str = Query(..., pattern="^(brochure|regulator_filing|crm_export)$"),
                       file: UploadFile = File(...)):
    kind, d = _find(set_id)
    if kind != "user":
        raise ApiError(403, "read_only", "Sample sets are read-only.")
    data = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise ApiError(413, "file_too_large", "File is too large.")
    if doc_type == "crm_export":
        ext = ".xlsx" if data[:2] == b"PK" else ".csv"
    else:
        if not data.startswith(b"%PDF-"):
            raise ApiError(415, "not_a_pdf", "Brochure and filing must be PDF files.")
        ext = ".pdf"
    mf = json.loads((d / "manifest.json").read_text())
    name = f"{doc_type}{ext}"
    (d / name).write_bytes(data)
    mf["documents"] = [x for x in mf["documents"] if x["type"] != doc_type] + [{"type": doc_type, "file": name}]
    (d / "manifest.json").write_text(json.dumps(mf))
    return {"set_id": set_id, "documents": [x["type"] for x in mf["documents"]]}
