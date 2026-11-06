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


class Sourced(BaseModel, Generic[T]):
    value: Optional[T] = Field(None, description="Extracted value, or null if the document does not state it.")
    source_page: Optional[int] = Field(None, ge=1, description="1-based PDF page number where the value is stated.")
    source_quote: Optional[str] = Field(None, description="Exact verbatim text copied from that page.")

    @model_validator(mode="after")
    def _value_needs_source(self):
        if self.value is not None and (self.source_page is None or not (self.source_quote or "").strip()):
            raise ValueError("a non-null value must include source_page and a non-empty source_quote")
        return self


class Milestone(BaseModel):
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
    price: Sourced[float] = Field(..., description="Total purchase price in AED.")
    area_sqft: Sourced[float]
    handover_date: Sourced[date]
    grace_period_days: Sourced[int]
    delay_rate: Sourced[float] = Field(
        ..., description="Number only: percent per annum if delay_basis is percent_per_annum; "
                         "AED per sq ft per year if fixed_per_sqft_per_year.")
    delay_basis: Sourced[DelayBasis]
    delay_cap: Sourced[float] = Field(
        ..., description="Cap on delay compensation as a percentage of the purchase price; null if no cap.")
    payment_plan: list[Milestone]
    cancellation_clause: Sourced[str] = Field(
        ..., description="Short summary of the buyer cancellation/termination clause; null if absent.")


class ContractData(ExtractionOutput):
    """Extraction output plus values computed deterministically in Python."""
    warnings: list[str] = Field(default_factory=list)
    payment_plan_percent_sum: Optional[float] = None
    source_file: Optional[str] = None
    file_hash: Optional[str] = None
    model: Optional[str] = None
