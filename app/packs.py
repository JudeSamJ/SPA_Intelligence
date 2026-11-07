"""Jurisdiction packs (versioned YAML) with schema validation, plus the dated rate tables they reference.

Statute rates, sections and thresholds live ONLY here (rules/packs/*.yaml) and in rules/rates/*.yaml.
Every entry carries: statute, section, description, formula, effective_from, source_url, reviewed_by_lawyer.
"""
from __future__ import annotations

import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

from . import config

KNOWN_FORMULAS = {"interest_on_amounts_paid", "defect_liability_years", "advance_cap_pct"}


class PackEntry(BaseModel):
    id: str
    statute: str
    section: str
    description: str
    formula: Optional[dict[str, Any]]
    effective_from: Optional[date]
    source_url: str = Field(min_length=1)
    reviewed_by_lawyer: bool
    needs_legal_review: bool = False

    @field_validator("formula")
    @classmethod
    def _known(cls, v):
        if v is not None and v.get("type") not in KNOWN_FORMULAS:
            raise ValueError(f"unknown formula type {v.get('type')!r}")
        return v

    @model_validator(mode="after")
    def _todo_needs_review(self):
        if self.formula is None and not self.needs_legal_review:
            raise ValueError(f"{self.id}: an entry without a formula must set needs_legal_review: true")
        if self.statute.startswith("TODO") and not self.needs_legal_review:
            raise ValueError(f"{self.id}: a TODO statute must set needs_legal_review: true")
        return self

    @property
    def unreviewed(self) -> bool:
        return not self.reviewed_by_lawyer


class Pack(BaseModel):
    id: str
    name: str
    country: str
    jurisdiction: str
    currency: str
    version: str
    detect_keywords: list[str] = Field(default_factory=list)
    penalty: dict[str, Any]
    entries: list[PackEntry]

    def entry(self, entry_id: str) -> PackEntry | None:
        return next((e for e in self.entries if e.id == entry_id), None)

    def formula_entry(self, ftype: str) -> PackEntry | None:
        return next((e for e in self.entries if e.formula and e.formula.get("type") == ftype), None)


def packs_dir() -> Path:
    return config.RULES_DIR / "packs"


@lru_cache(maxsize=None)
def load_pack(pack_id: str) -> Pack:
    if not re.fullmatch(r"[a-z0-9_]+", pack_id or ""):
        raise KeyError(pack_id)
    path = packs_dir() / f"{pack_id}.yaml"
    if not path.exists():
        raise KeyError(pack_id)
    return Pack.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def list_packs() -> list[Pack]:
    return [load_pack(p.stem) for p in sorted(packs_dir().glob("*.yaml"))]


def detect_pack(pages: list[str]) -> tuple[str, str] | None:
    """(pack_id, matched_text) from the pack keyword lists, preferring the pack with the most specific hit.
    Order: packs with more distinctive keywords first (list order inside the YAML)."""
    text = "\n".join(pages)
    best = None
    for p in list_packs():
        for i, pat in enumerate(p.detect_keywords):
            m = re.search(pat, text, re.IGNORECASE)
            if m and (best is None or i < best[2]):
                best = (p.id, m.group(0), i)
    return (best[0], best[1]) if best else None


# --------------------------------------------------------------------------- rate tables
class RateUnavailable(ValueError):
    pass


def rates_dir() -> Path:
    return Path(os.environ.get("SPA_RATES_DIR") or config.RULES_DIR / "rates")


class RateTable(BaseModel):
    id: str
    name: str
    source: str = ""
    illustrative: bool = False
    rows: list[dict[str, Any]] = Field(default_factory=list)

    def sorted_rows(self) -> list[tuple[date, float]]:
        out = []
        for r in self.rows:
            d = r["effective_from"]
            out.append((d if isinstance(d, date) else date.fromisoformat(str(d)), float(r["rate_pct"])))
        return sorted(out)

    def segments(self, start: date, end: date) -> list[tuple[date, date, float]]:
        """Split [start, end) at rate changes. Raises RateUnavailable if no rate covers `start`."""
        rows = self.sorted_rows()
        if not rows or rows[0][0] > start:
            first = rows[0][0].isoformat() if rows else "no rows"
            raise RateUnavailable(f"Rate table '{self.id}' has no rate in effect on {start.isoformat()} "
                                  f"(earliest row: {first}). Add the dated rate to rules/rates/{self.id}.yaml.")
        out, cur = [], start
        while cur < end:
            rate = [r for d, r in rows if d <= cur][-1]
            nxt = min([d for d, _ in rows if d > cur] + [end])
            out.append((cur, nxt, rate))
            cur = nxt
        return out


def load_rate_table(table_id: str) -> RateTable:
    if not re.fullmatch(r"[a-z0-9_]+", table_id or ""):
        raise RateUnavailable("invalid rate table id")
    path = rates_dir() / f"{table_id}.yaml"
    if not path.exists():
        raise RateUnavailable(f"Rate table '{table_id}' not found ({path.name}).")
    return RateTable.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
