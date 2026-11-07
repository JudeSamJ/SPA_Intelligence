"""Docling (open-source document parser) -> page text -> LLM structured extraction. Optional dependency:
    pip install docling
If it is not installed the engine reports "not configured" (it is never simulated)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

from . import LLMEngineBase
from .. import config


class DoclingEngine(LLMEngineBase):
    name = "docling"
    description = "Docling open-source parse, then LLM structured extraction"

    def configured(self) -> tuple[bool, str]:
        if importlib.util.find_spec("docling") is None:
            return False, "optional dependency missing (pip install docling)"
        if not config.llm_configured():
            return False, config.setup_hint()
        return True, ""

    def parse_pages(self, pdf_path: Path):
        from docling.document_converter import DocumentConverter   # type: ignore
        doc = DocumentConverter().convert(str(pdf_path)).document
        n = doc.num_pages() if callable(getattr(doc, "num_pages", None)) else len(doc.pages)
        pages = [doc.export_to_markdown(page_no=i) for i in range(1, n + 1)]
        return pages, {}
