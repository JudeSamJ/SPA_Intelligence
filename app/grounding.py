"""Grounding: post-check every extracted field against the PDF text. Pure Python, no LLM.

Per field we run the checks that apply:
  (a) quote  - the quote exists on the stated page (normalised, then fuzzy above a threshold), or on another page
  (b) value  - amounts, percentages and dates in `value` appear in the quote, compared numerically / as ISO dates
  (c) entity - names and unit ids appear in the document text

Status:  grounded (all applicable checks pass, quote exact) | partial (quote only fuzzy-matched or on another page) |
         ungrounded (quote missing, value not in quote, or entity not in document) | not_stated (null, no quote)
Ungrounded -> value becomes null (the claim is kept in grounding.claimed_value for review) and a warning is added.
confidence / needs_review: see rules/grounding.yaml (weights, min_confidence).
"""
from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path

import yaml
from rapidfuzz import fuzz

from . import config
from .evidence import key, locate, set_fuzzy_threshold
from .schema import ContractData, Grounding, GroundingCheck, Milestone, Sourced

NUMERIC_FIELDS = {"price", "area_sqft", "grace_period_days", "delay_rate", "delay_cap"}
ENTITY_FIELDS = {"buyer", "unit_id", "registration_number"}
MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
     "november", "december"], 1)}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9
WORD_NUMS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
    "seventeen eighteen nineteen twenty".split())}
WORD_NUMS.update({"thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
                  "ninety": 90, "hundred": 100})
SCALE = {"million": 1e6, "mn": 1e6, "m": 1e6, "lakh": 1e5, "lakhs": 1e5, "crore": 1e7, "crores": 1e7,
         "thousand": 1e3, "k": 1e3, "billion": 1e9}


@lru_cache(maxsize=1)
def cfg() -> dict:
    c = yaml.safe_load((config.RULES_DIR / "grounding.yaml").read_text())
    set_fuzzy_threshold(c["fuzzy_threshold"])
    return c


# ------------------------------------------------------------------ parsing
def parse_numbers(text: str) -> list[float]:
    """All numbers in text: 1,234.50 / 12,34,567 (Indian grouping) / '2.45 million' / 'sixty'."""
    out: list[float] = []
    for m in re.finditer(r"(\d[\d,]*(?:\.\d+)?)(?:\s*(million|billion|thousand|lakhs?|crores?|mn|k|m)\b)?",
                         text, re.IGNORECASE):
        raw = m.group(1).replace(",", "")
        try:
            v = float(raw)
        except ValueError:
            continue
        out.append(v)
        if m.group(2):
            out.append(v * SCALE[m.group(2).lower()])
    for w in re.findall(r"[a-z]+", text.lower()):
        if w in WORD_NUMS:
            out.append(float(WORD_NUMS[w]))
    return out


def parse_dates(text: str) -> list[date]:
    out: list[date] = []

    def add(y, mth, d):
        try:
            out.append(date(int(y), int(mth), int(d)))
        except ValueError:
            pass

    for m in re.finditer(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b", text):
        add(m[1], m[2], m[3])
    for m in re.finditer(r"\b(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})\b", text):     # day first (UAE/IN convention)
        add(m[3], m[2], m[1])
    pat_dmy = r"\b(\d{1,2})(?:st|nd|rd|th)?\s*(?:of\s+)?([A-Za-z]{3,9})\.?,?\s+(\d{4})\b"
    for m in re.finditer(pat_dmy, text):
        mo = MONTHS.get(m[2].lower())
        if mo:
            add(m[3], mo, m[1])
    for m in re.finditer(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})\b", text):
        mo = MONTHS.get(m[1].lower())
        if mo:
            add(m[3], mo, m[2])
    return out


# ------------------------------------------------------------------ checks
def _quote_check(pdf_bytes: bytes, pages: list[str], page: int | None, quote: str):
    """-> (check, evidence). Exact on stated page=1.0, other page=0.9, fuzzy<=0.8, none=0."""
    ev = locate(pdf_bytes, page, quote)
    qk = key(quote)
    pk = [key(p) for p in pages]
    if page and 1 <= page <= len(pk) and qk in pk[page - 1]:
        return GroundingCheck(name="quote_on_page", passed=True, detail=f"exact match on page {page}"), ev, 1.0
    for i, p in enumerate(pk, 1):
        if qk in p:
            return (GroundingCheck(name="quote_on_page", passed=True,
                                   detail=f"found on page {i}, not on stated page {page}"), ev, 0.9)
    best = max((fuzz.partial_ratio(qk, p) for p in pk), default=0.0)
    if best >= cfg()["fuzzy_threshold"]:
        return (GroundingCheck(name="quote_on_page", passed=True, detail=f"fuzzy match (score {best:.0f})"),
                ev, min(0.8, best / 100))
    return GroundingCheck(name="quote_on_page", passed=False, detail=f"quote not found (best score {best:.0f})"), ev, 0.0


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-6, abs(b) * 1e-9)


def _value_check(field: str, value, quote: str, basis: str | None = None):
    if value is None:
        return None
    if field == "delay_basis":
        pat = {"percent_per_annum": r"per\s+annum|p\.a\.|annum|per\s+year|%",
               "fixed_per_sqft_per_year": r"sq|square|feet|foot"}.get(value)
        if pat is None:
            return None
        ok = re.search(pat, quote, re.IGNORECASE) is not None
        return GroundingCheck(name="value_in_quote", passed=ok,
                              detail=f"basis '{value}' wording {'found' if ok else 'not found'} in quote")
    if field == "handover_date" or isinstance(value, date):
        d = value if isinstance(value, date) else date.fromisoformat(str(value))
        ok = d in parse_dates(quote)
        return GroundingCheck(name="value_in_quote", passed=ok,
                              detail=f"date {d.isoformat()} {'found' if ok else 'not found'} in quote")
    if isinstance(value, list) and value and all(isinstance(x, (int, float)) for x in value):
        nums = parse_numbers(quote)
        ok = all(any(_close(n, float(x)) for n in nums) for x in value)
        return GroundingCheck(name="value_in_quote", passed=ok,
                              detail=f"{len(value)} numbers {'all found' if ok else 'not all found'} in quote")
    if isinstance(value, (int, float)):
        ok = any(_close(n, float(value)) for n in parse_numbers(quote))
        return GroundingCheck(name="value_in_quote", passed=ok,
                              detail=f"number {value:g} {'found' if ok else 'not found'} in quote (parsed numerically)")
    return None   # free text (cancellation summary): no value check


def _entity_check(value: str, doc_key: str):
    vk = key(value)
    ok = bool(vk) and vk in doc_key
    if not ok and vk:
        ok = fuzz.partial_ratio(vk, doc_key) >= 97
    return GroundingCheck(name="entity_in_document", passed=ok,
                          detail=f"'{value}' {'appears' if ok else 'does not appear'} in the document text")


def _confidence(checks_scores: list[tuple[str, float]]) -> float:
    w = cfg()["weights"]
    tot = sum(w[n] for n, _ in checks_scores)
    return round(sum(w[n] * s for n, s in checks_scores) / tot, 3) if tot else 0.0


def ground_item(item, name: str, pdf_bytes: bytes, pages: list[str], doc_key: str, *,
                percent: float | None = None, due_date=None, basis: str | None = None) -> Grounding:
    """Mutates `item` (evidence, grounding, confidence, needs_review, value) and returns its Grounding."""
    quote = item.source_quote
    value = None if percent is not None or hasattr(item, "percent") or hasattr(item, "amount") else getattr(item, "value", None)
    if not quote or not quote.strip():
        g = Grounding(status="not_stated" if value is None else "ungrounded")
        item.grounding, item.confidence, item.needs_review = g, (1.0 if value is None else 0.0), value is not None
        item.evidence = None
        return g
    qchk, ev, qscore = _quote_check(pdf_bytes, pages, item.source_page, quote)
    checks, scores = [qchk], [("quote", qscore)]
    if hasattr(item, "amount"):                        # dated clause: the stated number must be in the quote
        ac = GroundingCheck(name="value_in_quote",
                            passed=any(_close(n, float(item.amount)) for n in parse_numbers(quote)),
                            detail=f"{item.amount} {item.unit} in clause quote")
        checks.append(ac); scores.append(("value", 1.0 if ac.passed else 0.0))
    elif hasattr(item, "percent"):                     # payment-plan row
        pc = GroundingCheck(name="value_in_quote",
                            passed=any(_close(n, float(item.percent)) for n in parse_numbers(quote)),
                            detail=f"percent {item.percent:g} in row quote")
        checks.append(pc); scores.append(("value", 1.0 if pc.passed else 0.0))
        if item.due_date is not None:
            dc = GroundingCheck(name="date_in_quote", passed=item.due_date in parse_dates(quote),
                                detail=f"due date {item.due_date.isoformat()} in row quote")
            checks.append(dc); scores.append(("value", 1.0 if dc.passed else 0.0))
    else:
        v = _value_check(name, value, quote)
        if v:
            checks.append(v); scores.append(("value", 1.0 if v.passed else 0.0))
        if name in ENTITY_FIELDS and value is not None:
            e = _entity_check(str(value), doc_key)
            checks.append(e); scores.append(("entity", 1.0 if e.passed else 0.0))
    failed = [c for c in checks if not c.passed]
    if failed:
        status = "ungrounded"
    elif qscore < 1.0:
        status = "partial"
    else:
        status = "grounded"
    conf = _confidence(scores)
    g = Grounding(status=status, checks=checks)
    item.evidence, item.grounding, item.confidence = ev, g, conf
    item.needs_review = status in ("partial", "ungrounded") or conf < cfg()["min_confidence"]
    if status == "ungrounded" and hasattr(item, "value") and value is not None:
        g.claimed_value = str(value)
        item.value = None                      # never a fact
    return g


def ground_contract(data: ContractData, pdf_bytes: bytes, pages: list[str]) -> ContractData:
    """Run all checks; add warnings. Idempotent (re-runnable on cached contracts, no LLM)."""
    cfg()
    doc_key = key("".join(pages))
    notes: list[str] = []
    keep = [w for w in data.warnings if not w.startswith(("Grounding:", "Quote for "))]
    for name in ("buyer", "unit_id", "price", "area_sqft", "handover_date", "grace_period_days", "delay_rate",
                 "delay_basis", "delay_cap", "cancellation_clause"):
        item: Sourced = getattr(data, name)
        if item.human_verified:
            continue
        g = ground_item(item, name, pdf_bytes, pages, doc_key)
        if g.status == "ungrounded":
            why = "; ".join(c.detail for c in g.checks if not c.passed) or "no source quote"
            notes.append(f"Grounding: '{name}' is ungrounded ({why}); value withheld (null).")
        elif item.needs_review:
            notes.append(f"Grounding: '{name}' needs review (confidence {item.confidence}).")
    kept_rows, bad_rows = [], list(data.ungrounded_rows)
    for i, m in enumerate(data.payment_plan, 1):
        if m.human_verified:
            kept_rows.append(m); continue
        g = ground_item(m, f"payment_plan[{i}]", pdf_bytes, pages, doc_key, percent=m.percent)
        if g.status == "ungrounded":
            bad_rows.append(m)
            notes.append(f"Grounding: payment-plan row '{m.name}' is ungrounded and was excluded from the plan.")
        else:
            kept_rows.append(m)
            if m.needs_review:
                notes.append(f"Grounding: payment-plan row '{m.name}' needs review.")
    data.payment_plan, data.ungrounded_rows = kept_rows, bad_rows
    keep_cl = []
    for i, cl in enumerate(data.dated_clauses, 1):
        if cl.human_verified:
            keep_cl.append(cl); continue
        g = ground_item(cl, f"dated_clauses[{i}]", pdf_bytes, pages, doc_key)
        if g.status == "ungrounded":
            notes.append(f"Grounding: dated clause '{cl.description}' is ungrounded and was dropped.")
        else:
            keep_cl.append(cl)
            if cl.needs_review:
                notes.append(f"Grounding: dated clause '{cl.description}' needs review.")
    data.dated_clauses = keep_cl
    detect_jurisdiction(data, pdf_bytes, pages, doc_key)
    data.grounded_version = 1
    data.warnings = keep + notes
    return data


def detect_jurisdiction(data: ContractData, pdf_bytes: bytes, pages: list[str], doc_key: str) -> None:
    """Keyword scan using each pack's detect_keywords. Sets jurisdiction_detected (with a quote) and currency."""
    from .packs import detect_pack, list_packs
    hit = detect_pack(pages)
    if not hit:
        data.jurisdiction_detected = Sourced()
        return
    pack_id, text = hit
    page = next((i for i, p in enumerate(pages, 1) if text.lower() in p.lower()), None)
    s = Sourced(value=pack_id, source_page=page, source_quote=text)
    ground_item(s, "jurisdiction", pdf_bytes, pages, doc_key)
    data.jurisdiction_detected = s
    data.currency = next((p.currency for p in list_packs() if p.id == pack_id), data.currency)
