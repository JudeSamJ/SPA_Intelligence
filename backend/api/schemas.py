"""Pydantic response/request models for the API (the OpenAPI schema is the contract with the frontend)."""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.schema import ContractData, Sourced

Status = Literal["not_extracted", "queued", "running", "extracted", "error"]


class ErrorBody(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorBody


class Health(BaseModel):
    status: Literal["ok"]
    llm_configured: bool
    model: str
    llm_calls_made: int
    llm_call_cap: int


class ContractSummary(BaseModel):
    id: str
    name: str
    source: Literal["sample", "upload"]
    size_bytes: int
    pages: int
    scanned_suspect: bool
    status: Status
    error: Optional[str] = None
    extracted_at: Optional[str] = None
    model: Optional[str] = None
    warnings_count: int = 0
    buyer: Optional[str] = None
    unit_id: Optional[str] = None
    price: Optional[float] = None


class ContractStatus(BaseModel):
    id: str
    status: Status
    error: Optional[str] = None
    llm_configured: bool
    model: str


class PlanRow(BaseModel):
    milestone: str
    percent: float
    amount: float
    due_date: Optional[date] = None
    trigger: Optional[str] = None
    type: Literal["handover_linked", "construction_linked", "time_based"]
    at_risk: bool
    source_page: int
    source_quote: str


class ContractDetail(BaseModel):
    id: str
    name: str
    pdf_url: str
    contract: ContractData
    plan: list[PlanRow]


class PenaltyRequest(BaseModel):
    scenarios: Optional[list[int]] = Field(None, max_length=20, description="Delay days; default from rules.")


class PenaltyTerms(BaseModel):
    rate: Sourced[float]
    basis: Sourced[str]
    grace_days: Sourced[int]
    cap_pct: Sourced[float]
    price: Sourced[float]
    area_sqft: Sourced[float]


class PenaltyRow(BaseModel):
    delay_days: int
    grace_days: int
    chargeable_days: int
    penalty: float
    cap_amount: Optional[float] = None
    cap_reached: bool
    pct_of_price: Optional[float] = None


class PenaltyResponse(BaseModel):
    terms: PenaltyTerms
    day_count_basis: int
    default_scenarios: list[int]
    rows: list[PenaltyRow]


class CashflowRequest(BaseModel):
    granularity: Literal["month", "quarter"] = "quarter"
    delay_days: Optional[int] = Field(None, ge=0, le=3650)


class Period(BaseModel):
    period: str
    amount_due: float
    at_risk_amount: float
    safe_amount: float
    cumulative: float
    cumulative_pct: float
    is_past: bool


class AtRisk(BaseModel):
    delay_days: int
    linked_amount: float
    linked_pct_of_plan: Optional[float] = None
    penalty_exposure: Optional[float] = None
    penalty_note: Optional[str] = None
    at_risk_total: float
    plan_total: float


class CashflowResponse(BaseModel):
    granularity: Literal["month", "quarter"]
    as_of: date
    price: float
    periods: list[Period]
    unscheduled: list[PlanRow]
    at_risk: AtRisk
    at_risk_definition: str
    max_delay_days: int


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)


class Citation(BaseModel):
    tool: str
    page: int
    quote: str


class ChatResponse(BaseModel):
    answer: str
    refused: bool
    citations: list[Citation]
    tool_calls: list[str]


class EvalField(BaseModel):
    correct: int
    total: int
    accuracy: float
    quote_valid: int
    quote_total: int
    quote_accuracy: Optional[float] = None


class EvalOverall(BaseModel):
    value_accuracy: Optional[float] = None
    checks: int
    quote_accuracy: Optional[float] = None
    quotes_checked: int


class PenaltyTests(BaseModel):
    passed: int
    failed: int
    total: int
    pass_rate: Optional[float] = None


class EvalResults(BaseModel):
    generated_at: str
    model: str
    files: list[str]
    fields: dict[str, EvalField]
    overall: EvalOverall
    penalty_tests: PenaltyTests
    per_file: dict[str, dict[str, bool]]


class EvalRunRequest(BaseModel):
    allow_llm: bool = False
    use_cache: bool = True


class EvalRunStatus(BaseModel):
    state: Literal["idle", "running", "done", "error"]
    done: int = 0
    total: int = 0
    message: Optional[str] = None
