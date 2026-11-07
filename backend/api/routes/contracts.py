from __future__ import annotations

import json
from datetime import datetime, timezone

import pymupdf
from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.cashflow import CashflowUnavailable, milestone_rows
from app.extract import load_cached
from backend.api import deps, persistence
from backend.api.deps import ApiError
from backend.api.schemas import ContractDetail, ContractStatus, ContractSummary, PlanRow

router = APIRouter(prefix="/contracts", tags=["contracts"])


def _summary(src: deps.Source) -> ContractSummary:
    status, err = deps.status_for(src)
    c = load_cached(src.path.read_bytes()) if status == "extracted" else None
    return ContractSummary(
        id=src.id, name=src.name, source=src.kind, size_bytes=src.size, pages=src.pages,
        scanned_suspect=src.scanned_suspect, status=status, error=err,
        extracted_at=c.extracted_at if c else None, model=c.model if c else None,
        warnings_count=len(c.warnings) if c else 0,
        buyer=c.buyer.value if c else None, unit_id=c.unit_id.value if c else None,
        price=c.price.value if c else None)


def _plan(contract) -> list[PlanRow]:
    try:
        rows = milestone_rows(contract)
    except CashflowUnavailable:
        return []
    return [PlanRow(**r | {"source_quote": m.source_quote}) for r, m in zip(rows, contract.payment_plan)]


@router.get("", response_model=list[ContractSummary])
def list_contracts():
    return [_summary(s) for s in deps.list_sources()]


@router.post("/upload", response_model=ContractStatus, status_code=202,
             dependencies=[Depends(deps.upload_limiter)])
async def upload(file: UploadFile = File(...), extract: bool = Query(True)):
    data = bytearray()
    while chunk := await file.read(1024 * 1024):
        data += chunk
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise ApiError(413, "file_too_large", f"PDF must be at most {config.MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    data = bytes(data)
    if not data.startswith(b"%PDF-"):
        raise ApiError(415, "not_a_pdf", "Only PDF files are accepted.")
    try:
        with pymupdf.open(stream=data, filetype="pdf") as doc:
            pages = doc.page_count
    except Exception:  # noqa: BLE001
        raise ApiError(415, "not_a_pdf", "The file could not be read as a PDF.") from None
    if pages < 1 or pages > config.MAX_UPLOAD_PAGES:
        raise ApiError(413, "too_many_pages", f"PDF must have between 1 and {config.MAX_UPLOAD_PAGES} pages.")

    cid = deps.sha256(data)
    config.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = config.UPLOAD_DIR / f"{cid}.pdf"
    if not path.exists():
        path.write_bytes(data)
        path.with_suffix(".meta.json").write_text(json.dumps({
            "name": deps.sanitize_filename(file.filename or ""),
            "uploaded_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}))
    src = deps.get_source(cid)
    persistence.flush_soon()                                     # keep the uploaded PDF safe before the slow extraction
    if extract and deps.status_for(src)[0] == "not_extracted":
        _start(src, force=False)
    status, err = deps.status_for(src)
    return ContractStatus(id=cid, status=status, error=err, llm_configured=config.llm_configured(),
                          model=config.model_tag())


def _start(src: deps.Source, force: bool):
    if src.scanned_suspect:
        raise ApiError(422, "scanned_pdf", "This PDF looks scanned (almost no extractable text). "
                                           "Scanned documents are not supported yet.")
    if not config.llm_configured():
        raise ApiError(503, "llm_not_configured", config.setup_hint())
    return deps.start_extraction(src, force)


@router.get("/{contract_id}/status", response_model=ContractStatus)
def status(contract_id: str):
    src = deps.get_source(contract_id)
    s, err = deps.status_for(src)
    return ContractStatus(id=src.id, status=s, error=err, llm_configured=config.llm_configured(),
                          model=config.model_tag())


@router.post("/{contract_id}/extract", response_model=ContractStatus, status_code=202)
def extract(contract_id: str, force: bool = Query(False)):
    src = deps.get_source(contract_id)
    if not force and deps.status_for(src)[0] == "extracted":
        return ContractStatus(id=src.id, status="extracted", llm_configured=config.llm_configured(),
                              model=config.model_tag())
    _start(src, force)
    s, err = deps.status_for(src)
    return ContractStatus(id=src.id, status=s, error=err, llm_configured=config.llm_configured(),
                          model=config.model_tag())


@router.get("/{contract_id}", response_model=ContractDetail)
def detail(contract_id: str):
    src, c = deps.get_contract(contract_id)
    return ContractDetail(id=src.id, name=src.name, pdf_url=f"/api/contracts/{src.id}/pdf",
                          contract=c, plan=_plan(c))


@router.get("/{contract_id}/pdf")
def pdf(contract_id: str):
    src = deps.get_source(contract_id)
    return FileResponse(src.path, media_type="application/pdf",
                        headers={"Content-Disposition": f'inline; filename="{src.id[:12]}.pdf"'})
