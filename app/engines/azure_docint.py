"""Azure Document Intelligence (prebuilt-layout) -> page text -> LLM structured extraction.
Enabled only if AZURE_DOCINT_ENDPOINT and AZURE_DOCINT_KEY are set. Uses the REST API directly (httpx)."""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx

from . import LLMEngineBase
from ..extract import ExtractionError
from .. import config

API_VERSION = os.environ.get("AZURE_DOCINT_API_VERSION") or "2024-11-30"


class AzureDocIntEngine(LLMEngineBase):
    name = "azure_docint"
    description = "Azure Document Intelligence layout, then LLM structured extraction"
    transport: httpx.BaseTransport | None = None      # tests inject a mock transport

    def configured(self) -> tuple[bool, str]:
        missing = [v for v in ("AZURE_DOCINT_ENDPOINT", "AZURE_DOCINT_KEY") if not os.environ.get(v)]
        if missing:
            return False, "set " + ", ".join(missing)
        if not config.llm_configured():
            return False, config.setup_hint()
        return True, ""

    def parse_pages(self, pdf_path: Path):
        endpoint = os.environ["AZURE_DOCINT_ENDPOINT"].rstrip("/")
        headers = {"Ocp-Apim-Subscription-Key": os.environ["AZURE_DOCINT_KEY"], "Content-Type": "application/pdf"}
        url = f"{endpoint}/documentintelligence/documentModels/prebuilt-layout:analyze?api-version={API_VERSION}"
        with httpx.Client(timeout=60, transport=self.transport) as c:
            r = c.post(url, headers=headers, content=pdf_path.read_bytes())
            if r.status_code != 202:
                raise ExtractionError(f"Document Intelligence returned HTTP {r.status_code}")
            op = r.headers["operation-location"]
            for _ in range(60):
                s = c.get(op, headers={"Ocp-Apim-Subscription-Key": headers["Ocp-Apim-Subscription-Key"]}).json()
                if s.get("status") == "succeeded":
                    pages = [" ".join(ln.get("content", "") for ln in p.get("lines", [])) for p in
                             s["analyzeResult"].get("pages", [])]
                    return pages, {"docint_pages": len(pages)}
                if s.get("status") == "failed":
                    raise ExtractionError("Document Intelligence analysis failed")
                time.sleep(1)
        raise ExtractionError("Document Intelligence timed out")
