"""Extraction engines behind one interface:  extract(pdf_path) -> ContractData + metrics.

Engines: claude_pdf (the configured LLM reads the PDF text directly; id kept from the original design),
azure_docint (Azure Document Intelligence layout, then LLM structured extraction), docling (open-source parse,
then LLM structured extraction). An engine that is not configured is reported as "not configured": never faked.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Protocol

import yaml

from .. import config
from ..extract import ExtractionError, extract_from_llm, file_hash, load_cached, pdf_pages, postprocess
from ..llm import usage_totals
from ..schema import ContractData


@dataclass
class ExtractionResult:
    contract: ContractData
    metrics: dict = field(default_factory=dict)


class Extractor(Protocol):
    name: str
    description: str
    uses_llm_cache: bool

    def configured(self) -> tuple[bool, str]: ...
    def extract(self, pdf_path: Path, use_cache: bool = True, source_name: str | None = None) -> ExtractionResult: ...


def pricing() -> dict:
    return yaml.safe_load((config.RULES_DIR / "pricing.yaml").read_text())


def cost_usd(tokens_in: int, tokens_out: int, pages: int, docint_pages: int = 0) -> float | None:
    """Estimated cost from REAL usage x configurable constants. None when constants are not set."""
    p = pricing()
    parts, ok = 0.0, False
    li, lo = p["llm"]["input_per_million_tokens"], p["llm"]["output_per_million_tokens"]
    if li is not None and lo is not None:
        parts += tokens_in / 1e6 * li + tokens_out / 1e6 * lo
        ok = True
    if docint_pages:
        dp = p["docint"]["layout_per_1000_pages"]
        if dp is None:
            return None
        parts += docint_pages / 1000 * dp
        ok = True
    return round(parts, 6) if ok else None


def build_contract(out, pdf_bytes: bytes, pages: list[str], name: str | None) -> ContractData:
    data = ContractData(**out.model_dump(), source_file=name, file_hash=file_hash(pdf_bytes), model=config.model_tag(),
                        extracted_at=datetime.now().isoformat(timespec="seconds"))
    return postprocess(data, pages, pdf_bytes)


class LLMEngineBase:
    name = ""
    description = ""
    uses_llm_cache = False

    def parse_pages(self, pdf_path: Path) -> tuple[list[str], dict]:
        raise NotImplementedError

    def configured(self) -> tuple[bool, str]:
        return (True, "") if config.llm_configured() else (False, config.setup_hint())

    def extract(self, pdf_path: Path, use_cache: bool = True, source_name: str | None = None) -> ExtractionResult:
        ok, why = self.configured()
        if not ok:
            raise ExtractionError(f"Engine '{self.name}' is not configured: {why}")
        pdf = pdf_path.read_bytes()
        t0, u0 = time.perf_counter(), usage_totals()
        pages, extra = self.parse_pages(pdf_path)
        parse_s = time.perf_counter() - t0
        out = extract_from_llm(pdf, pages=pages)
        contract = build_contract(out, pdf, pdf_pages(pdf), source_name or pdf_path.name)   # grounded against the PDF itself
        u1 = usage_totals()
        tin, tout = u1["input_tokens"] - u0["input_tokens"], u1["output_tokens"] - u0["output_tokens"]
        n = len(pdf_pages(pdf))
        return ExtractionResult(contract, {
            "engine": self.name, "latency_s": round(time.perf_counter() - t0, 3), "parse_s": round(parse_s, 3),
            "pages": n, "input_tokens": tin, "output_tokens": tout, "llm_calls": u1["calls"] - u0["calls"],
            "cost_usd": cost_usd(tin, tout, n, extra.get("docint_pages", 0)), "cached": False, **extra})


class ClaudePdfEngine:
    """The existing path: the configured LLM reads the PDF's text page by page (with the PDF itself for Anthropic)."""
    name = "claude_pdf"
    description = "Configured LLM reads the PDF directly (existing pipeline)"
    uses_llm_cache = True

    def configured(self) -> tuple[bool, str]:
        return (True, "") if config.llm_configured() else (False, config.setup_hint())

    def extract(self, pdf_path: Path, use_cache: bool = True, source_name: str | None = None) -> ExtractionResult:
        from ..extract import extract_contract
        pdf = pdf_path.read_bytes()
        cached = use_cache and load_cached(pdf) is not None
        t0, u0 = time.perf_counter(), usage_totals()
        c = extract_contract(pdf, source_name or pdf_path.name, use_cache=use_cache)
        u1 = usage_totals()
        tin, tout = u1["input_tokens"] - u0["input_tokens"], u1["output_tokens"] - u0["output_tokens"]
        n = len(pdf_pages(pdf))
        return ExtractionResult(c, {"engine": self.name, "latency_s": 0.0 if cached else round(time.perf_counter() - t0, 3),
                                    "pages": n, "input_tokens": tin, "output_tokens": tout,
                                    "llm_calls": u1["calls"] - u0["calls"], "cached": cached,
                                    "cost_usd": None if cached else cost_usd(tin, tout, n)})


def get_engine(name: str):
    from .azure_docint import AzureDocIntEngine
    from .docling_engine import DoclingEngine
    engines = {"claude_pdf": ClaudePdfEngine, "azure_docint": AzureDocIntEngine, "docling": DoclingEngine}
    if name not in engines:
        raise KeyError(f"unknown engine '{name}'")
    return engines[name]()


def list_engines() -> list[dict]:
    out = []
    for n in ("claude_pdf", "azure_docint", "docling"):
        e = get_engine(n)
        ok, why = e.configured()
        out.append({"name": n, "description": e.description, "configured": ok,
                    "reason": "" if ok else f"not configured: {why}"})
    return out
