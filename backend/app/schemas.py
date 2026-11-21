"""Pydantic schemas shared by every module. One file so module contracts are explicit."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Department(str, Enum):
    DUTY_OPS = "Duty Ops"
    SOURCING = "Sourcing"
    BILLING = "Billing"
    SALES = "Sales"


class Category(str, Enum):
    CARE_GAP = "care_gap"  # dependant (elder / child) without the scheduled carer
    SERVICE_GAP = "service_gap"  # missed / late non-care service
    ARRIVAL_CONFIRMED = "arrival_confirmed"  # family confirmed the helper arrived
    SCHEDULE_CHANGE = "schedule_change"
    REFUND_QUERY = "refund_query"
    NEW_ENQUIRY = "new_enquiry"
    UNIDENTIFIED_BOOKING = "unidentified_booking"
    OTHER = "other"


class Urgency(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    NONE = "none"


URGENCY_ORDER = {Urgency.CRITICAL: 0, Urgency.HIGH: 1, Urgency.MEDIUM: 2, Urgency.LOW: 3, Urgency.NONE: 4}


class ActionCode(str, Enum):
    CARE_GAP_IMMEDIATE = "CARE_GAP_IMMEDIATE"
    CARE_GAP_COVERED_CHASE_SOURCING = "CARE_GAP_COVERED_CHASE_SOURCING"
    SERVICE_GAP_CHECK_ARRIVAL = "SERVICE_GAP_CHECK_ARRIVAL"
    CLOSE_CONFIRMED_ARRIVAL = "CLOSE_CONFIRMED_ARRIVAL"
    SCHEDULE_CHANGE_SOURCING_CHECK = "SCHEDULE_CHANGE_SOURCING_CHECK"
    BILLING_VERIFY_DISPUTED_REFUND = "BILLING_VERIFY_DISPUTED_REFUND"
    RELAY_APPROVED_REFUND_CHASE_PAYOUT = "RELAY_APPROVED_REFUND_CHASE_PAYOUT"
    RELAY_CONFIRMED_REFUND_FACTS = "RELAY_CONFIRMED_REFUND_FACTS"
    SALES_ENQUIRY_NO_QUOTE = "SALES_ENQUIRY_NO_QUOTE"
    ASK_MINIMUM_BOOKING_IDENTITY = "ASK_MINIMUM_BOOKING_IDENTITY"
    MANUAL_TRIAGE = "MANUAL_TRIAGE"


class Channel(str, Enum):
    PHONE = "phone"
    WHATSAPP = "whatsapp"
    NONE = "none"


class IssueStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    AWAITING_INFO = "awaiting_info"


# ---------------------------------------------------------------- data quality
class DQIssue(BaseModel):
    source_file: str
    record_id: str
    field: str
    original_value: str | None
    normalised_value: str | None = None
    issue_type: Literal[
        "missing_column", "missing_value", "invalid_format", "duplicate", "orphan_reference",
        "normalised", "chronology", "reconciliation", "encoding", "cross_reference",
    ]
    problem: str
    severity: Literal["info", "warning", "error"]
    recommended_action: str
    human_review_required: bool


# ---------------------------------------------------------------- source records
class BookingFacts(BaseModel):
    """Facts DERIVED from the register text by deterministic parsing (never by the LLM)."""

    booking_closed: bool = False
    arrival_confirmed: bool | None = None  # None = register says nothing
    substitute_confirmed: bool | None = None
    confirmed_start_time: str | None = None
    refund_status: Literal["approved", "under_review", "no_record"] = "no_record"
    refund_amount: str | None = None
    payment_amount: str | None = None
    payout_date: str | None = None
    payout_date_recorded: bool = False
    sourcing_checking: bool = False


class BookingRecord(BaseModel):
    booking_id: str
    service: str | None
    locality: str | None
    scheduled_start_ist: datetime | None
    updated_at_ist: datetime | None
    operations_record: str | None
    billing_record: str | None
    raw: dict[str, str | None]  # exact original strings
    facts: BookingFacts = Field(default_factory=BookingFacts)
    row_number: int


class Message(BaseModel):
    event_id: str
    received_at_ist: datetime | None
    thread_id: str | None
    booking_id: str | None
    channel: str | None
    sender: str | None
    message: str  # original text, unchanged
    text_normalised: str  # derived: unicode quotes/whitespace normalised, lowercased copy
    is_internal: bool
    raw: dict[str, str | None]
    row_number: int


class IngestResult(BaseModel):
    bookings: list[BookingRecord]
    messages: list[Message]
    dq_issues: list[DQIssue]
    files: dict[str, dict[str, Any]]


# ---------------------------------------------------------------- grouping
class BookingMatch(BaseModel):
    status: Literal["matched", "unknown_reference", "no_reference"]
    booking_id: str | None = None
    possible_candidates: list[str] = Field(default_factory=list)
    note: str


class IssueGroup(BaseModel):
    issue_id: str
    thread_ids: list[str]
    booking_id: str | None
    source_message_ids: list[str]
    grouping_reasons: list[str]
    booking_match: BookingMatch


class IssueContext(BaseModel):
    group: IssueGroup
    messages: list[Message]
    booking: BookingRecord | None


# ---------------------------------------------------------------- signals & recommendations
class Signals(BaseModel):
    """Interpretation of the messages. Produced by keyword rules OR by the LLM."""

    issue_category: Category
    customer_intent: str
    resolved_by_customer: bool = False
    cover_available: Literal["yes", "no", "unknown", "not_applicable"] = "unknown"
    cover_until: str | None = None
    deadline: str | None = None  # HH:MM by which harm / need occurs
    contact_preference: Literal["phone", "whatsapp", "no_preference"] = "no_preference"
    refund_claimed_approved: bool = False
    mentions_today: bool = False
    requested_change: str | None = None
    source: Literal["rules", "ai"] = "rules"


class EvidenceItem(BaseModel):
    source_id: str
    kind: Literal["message", "booking", "rule"]
    quote: str


class GuardrailEvent(BaseModel):
    rule_id: str
    field: str
    original: Any = None
    enforced: Any = None
    reason: str


class Recommendation(BaseModel):
    issue_category: Category
    customer_intent: str
    status: IssueStatus
    urgency: Urgency
    priority_rank: int | None = None
    priority_reason: str = ""
    responsible_department: Department
    supporting_departments: list[Department] = Field(default_factory=list)
    action_code: ActionCode
    next_action: str
    contact_channel: Channel
    missing_information: list[str] = Field(default_factory=list)
    draft_response: str | None = None
    hold_contact_reason: str | None = None
    explanation: str = ""
    evidence: list[EvidenceItem] = Field(default_factory=list)
    human_review_required: bool = True
    human_review_reasons: list[str] = Field(default_factory=list)
    guardrail_events: list[GuardrailEvent] = Field(default_factory=list)
    source: Literal["rules", "ai_guarded", "ai_raw", "rules_fallback", "human"] = "rules"
    confidence: float | None = None
    deadline: str | None = None
    signals: Signals | None = None


# ---------------------------------------------------------------- LLM
class AITriageOutput(BaseModel):
    """Strict schema the model must return. Validated with Pydantic; extra keys ignored."""

    model_config = ConfigDict(extra="ignore")

    issue_category: Category
    customer_intent: str = Field(min_length=3, max_length=400)
    resolved_by_customer: bool
    cover_available: Literal["yes", "no", "unknown", "not_applicable"]
    cover_until: str | None = None
    deadline: str | None = None
    contact_preference: Literal["phone", "whatsapp", "no_preference"]
    refund_claimed_approved: bool
    mentions_today: bool
    requested_change: str | None = None
    suggested_urgency: Urgency
    suggested_department: Department
    recommended_action_code: ActionCode
    recommended_next_action: str = Field(min_length=3, max_length=600)
    missing_information: list[str] = Field(default_factory=list, max_length=10)
    draft_response: str | None = Field(default=None, max_length=1200)
    hold_contact_reason: str | None = None
    explanation: str = Field(min_length=3, max_length=1200)
    supporting_source_ids: list[str] = Field(min_length=1)
    confidence: float | None = Field(default=None, ge=0, le=1)


class LLMCallRecord(BaseModel):
    call_id: str
    issue_id: str | None
    ok: bool
    provider: str
    model_requested: str
    model_used: str | None = None
    provider_upstream: str | None = None
    generation_id: str | None = None
    started_at: str
    duration_ms: int
    attempts: int
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None  # only when the provider returned it
    finish_reason: str | None = None
    error_type: str | None = None
    error_message: str | None = None
    request_messages: list[dict[str, Any]] = Field(default_factory=list)
    raw_content: str | None = None
    raw_response: dict[str, Any] | None = None
    validation_errors: list[str] = Field(default_factory=list)
    simulated: bool = False  # True ONLY for tests with fake transports; never shown as real


# ---------------------------------------------------------------- runs
class IssueResult(BaseModel):
    issue_id: str
    group: IssueGroup
    messages: list[Message]
    booking: BookingRecord | None
    rules: Recommendation
    ai_raw: Recommendation | None = None
    ai_guarded: Recommendation | None = None
    ai_status: Literal["not_run", "ok", "failed", "skipped"] = "not_run"
    ai_error: str | None = None
    ai_call_id: str | None = None
    final: Recommendation


class RunResult(BaseModel):
    run_id: str
    dataset: str = "supplied"
    mode: Literal["rules", "ai"]
    variant: str  # e.g. rules_v1, ai_prompt_v1
    started_at: str
    finished_at: str
    status: Literal["completed", "completed_with_fallback", "failed"]
    model: str | None = None
    notes: list[str] = Field(default_factory=list)
    issues: list[IssueResult]
    llm_calls: list[LLMCallRecord] = Field(default_factory=list)
    recorded: bool = False  # True when loaded from a saved artifact instead of executed now


# ---------------------------------------------------------------- review
class ReviewRequest(BaseModel):
    action: Literal[
        "approve", "change_priority", "change_department", "correct_action",
        "edit_draft", "request_info", "resolve", "reopen",
    ]
    reason: str | None = Field(default=None, max_length=1000)
    reviewer: str = Field(default="coordinator", max_length=80)
    urgency: Urgency | None = None
    department: Department | None = None
    action_code: ActionCode | None = None
    next_action: str | None = Field(default=None, max_length=600)
    draft_response: str | None = Field(default=None, max_length=1500)
    info_requested: str | None = Field(default=None, max_length=600)


class ReviewRecord(ReviewRequest):
    review_id: int
    issue_id: str
    run_id: str
    created_at: str
    before: dict[str, Any] = Field(default_factory=dict)

