"""Pydantic models for extracted contract data.

Rule: every extracted value carries source_page and source_quote. A value of None means
the document does not state it (never guessed). A None value MAY still carry a quote when
the contract explicitly says there is none (e.g. "not subject to any cap").
"""
from __future__ import annotations

from datetime import date
from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, Field, model_validator

T = TypeVar("T")

DelayBasis = Literal["percent_per_annum", "fixed_per_sqft_per_year", "other"]


GroundingStatus = Literal["grounded", "partial", "ungrounded", "not_stated"]
# Fields that the app adds AFTER the model answers. They are removed from the tool schema sent to the LLM.
TRUST_FIELDS = ("evidence", "grounding", "confidence", "needs_review", "human_verified", "review")


class Evidence(BaseModel):
    """Where a value is printed. Computed server-side from the PDF, never by the LLM."""
    page: Optional[int] = None
    quote: Optional[str] = None
    bbox: Optional[list[float]] = Field(None, description="[x0,y0,x1,y1] union box in PDF points, or null.")
    rects: list[list[float]] = Field(default_factory=list, description="One rect per text line (PDF points).")
    page_width: Optional[float] = None
    page_height: Optional[float] = None
    method: Optional[str] = Field(None, description="exact | fuzzy | not_found")


class GroundingCheck(BaseModel):
    name: str
    passed: bool
    detail: str = ""


class Grounding(BaseModel):
    status: GroundingStatus = "not_stated"
    checks: list[GroundingCheck] = Field(default_factory=list)
    claimed_value: Optional[str] = Field(None, description="What the model claimed, kept only when ungrounded.")


class ReviewMark(BaseModel):
    action: Literal["accept", "correct", "reject"]
    note: str = ""
    reviewer: str = ""
    at: str = ""


class TrustMixin(BaseModel):
    evidence: Optional[Evidence] = None
    grounding: Optional[Grounding] = None
    confidence: Optional[float] = Field(None, ge=0, le=1)
    needs_review: bool = False
    human_verified: bool = False
    review: Optional[ReviewMark] = None


class Sourced(TrustMixin, Generic[T]):
    value: Optional[T] = Field(None, description="Extracted value, or null if the document does not state it.")
    source_page: Optional[int] = Field(None, ge=1, description="1-based PDF page number where the value is stated.")
    source_quote: Optional[str] = Field(None, description="Exact verbatim text copied from that page.")

    @model_validator(mode="after")
    def _value_needs_source(self):
        if self.value is not None and (self.source_page is None or not (self.source_quote or "").strip()):
            raise ValueError("a non-null value must include source_page and a non-empty source_quote")
        return self


class Milestone(TrustMixin):
    name: str
    percent: float = Field(..., ge=0, le=100, description="Percentage of the purchase price.")
    due_date: Optional[date] = Field(None, description="ISO date stated for this milestone, else null.")
    trigger: Optional[str] = Field(None, description="Event that triggers the payment, as stated, else null.")
    source_page: int = Field(..., ge=1)
    source_quote: str = Field(..., min_length=1, description="Verbatim text of the payment-plan row.")


class ExtractionOutput(BaseModel):
    """What the LLM returns (and nothing computed)."""
    buyer: Sourced[str]
    unit_id: Sourced[str]
    price: Sourced[float] = Field(..., description="Total purchase price in the currency printed in the contract (a bare number).")
    area_sqft: Sourced[float]
    handover_date: Sourced[date]
    grace_period_days: Sourced[int]
    delay_rate: Sourced[float] = Field(
        ..., description="Number only: percent per annum if delay_basis is percent_per_annum; "
                         "currency units per sq ft per year if fixed_per_sqft_per_year.")
    delay_basis: Sourced[DelayBasis]
    delay_cap: Sourced[float] = Field(
        ..., description="Cap on delay compensation as a percentage of the purchase price; null if no cap.")
    payment_plan: list[Milestone]
    cancellation_clause: Sourced[str] = Field(
        ..., description="Short summary of the buyer cancellation/termination clause; null if absent.")


class ContractData(ExtractionOutput):
    """Extraction output plus values computed deterministically in Python."""
    warnings: list[str] = Field(default_factory=list)
    ungrounded_rows: list[Milestone] = Field(default_factory=list, description="Payment-plan rows that failed grounding.")
    jurisdiction_detected: Sourced[str] = Field(default_factory=Sourced, description="Pack id found by keyword scan.")
    jurisdiction: Optional[str] = Field(None, description="Pack id chosen by the user (overrides detection).")
    currency: Optional[str] = None
    payment_plan_percent_sum: Optional[float] = None
    source_file: Optional[str] = None
    file_hash: Optional[str] = None
    model: Optional[str] = None
    extracted_at: Optional[str] = None   # local time of the LLM extraction
