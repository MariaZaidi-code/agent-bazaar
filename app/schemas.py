from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


class ClaimLabel(str, Enum):
    verified = "Verified"
    supported = "Supported"
    contradicted = "Contradicted"
    unsupported = "Unsupported"


class TaskStatus(str, Enum):
    completed = "completed"
    partial = "partial"
    failed = "failed"


class StepStatus(str, Enum):
    pending = "pending"
    completed = "completed"
    failed = "failed"
    substituted = "substituted"
    skipped = "skipped"


class BreakerStatus(str, Enum):
    closed = "closed"
    open = "open"
    half_open = "half-open"


class ConceptSpec(BaseModel):
    concept: str
    name: str = ""
    unit: str | None = None
    datatype: str = "string"
    required: bool = True
    description: str = ""
    fields: list[str] = Field(default_factory=list)


class ClaimSpec(BaseModel):
    text: str
    label: ClaimLabel | None = None
    evidence: str = ""
    checked_at: datetime | None = None


class ToolSpec(BaseModel):
    id: str
    name: str
    provider_id: str
    description: str
    capability: str
    inputs: list[ConceptSpec] = Field(default_factory=list)
    outputs: list[ConceptSpec] = Field(default_factory=list)
    claims: list[ClaimSpec] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    docs_url: str = ""
    price: float = 0.0
    probe_eligible: bool = True
    execution: Literal["live", "fixture", "mock"] = "live"
    tags: list[str] = Field(default_factory=list)

    @property
    def search_text(self) -> str:
        pieces = [
            self.name,
            self.description,
            self.capability,
            " ".join(self.keywords),
            " ".join(f"{i.concept} {i.description}" for i in self.inputs),
            " ".join(f"{o.concept} {o.description}" for o in self.outputs),
        ]
        return " ".join(pieces)

    def claim_labels(self) -> list[ClaimLabel]:
        return [claim.label for claim in self.claims if claim.label is not None]


class BaseMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: new_id("msg"))
    timestamp: datetime = Field(default_factory=utcnow)
    sender: str
    recipient: str | None = None
    correlation_id: str
    kind: str


class TaskRequestMessage(BaseMessage):
    kind: str = "TaskRequest"
    task_id: str
    task: str


class Candidate(BaseModel):
    tool: ToolSpec
    relevance: float = 0.0
    trust: float = 0.5
    score: float = 0.0
    rank: int = 0
    reasons: list[str] = Field(default_factory=list)
    claim_label: ClaimLabel = ClaimLabel.unsupported
    breaker_state: BreakerStatus = BreakerStatus.closed
    demoted: bool = False
    eligible: bool = True


class CandidateList(BaseMessage):
    kind: str = "CandidateList"
    task_id: str
    subgoal_id: str
    capability: str
    candidates: list[Candidate] = Field(default_factory=list)


class VerifyRequestMessage(BaseMessage):
    kind: str = "VerifyRequest"
    task_id: str
    subgoal_id: str
    candidates: list[Candidate] = Field(default_factory=list)


class ClaimVerification(BaseModel):
    tool_id: str
    claim: str
    label: ClaimLabel
    evidence: str = ""


class VerifyResultMessage(BaseMessage):
    kind: str = "VerifyResult"
    task_id: str
    labels: dict[str, list[ClaimVerification]] = Field(default_factory=dict)
    overall: dict[str, ClaimLabel] = Field(default_factory=dict)
    drift_alerts: list[str] = Field(default_factory=list)


class ServiceOfferMessage(BaseMessage):
    kind: str = "ServiceOffer"
    provider_id: str
    tool_id: str
    capability: str
    price: float = 0.0
    claims: list[ClaimSpec] = Field(default_factory=list)


class ServiceCallMessage(BaseMessage):
    kind: str = "ServiceCall"
    task_id: str
    step_id: str
    tool_id: str
    params: dict[str, Any] = Field(default_factory=dict)


class ServiceResultMessage(BaseMessage):
    kind: str = "ServiceResult"
    task_id: str
    step_id: str
    tool_id: str
    status: Literal["success", "error"] = "success"
    data: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False
    source: str = "live"


class FeedbackMessage(BaseMessage):
    kind: str = "Feedback"
    task_id: str
    tool_id: str
    outcome: Literal["success", "failure"]
    schema_valid: bool = True
    rating: float | None = None


class TrustUpdateMessage(BaseMessage):
    kind: str = "TrustUpdate"
    provider_id: str
    signal: str
    success: bool
    weight: float | None = None
    reason: str = ""
    source: str = "execution"


class DriftAlertMessage(BaseMessage):
    kind: str = "DriftAlert"
    alert_id: str = Field(default_factory=lambda: new_id("drift"))
    tool_id: str
    provider_id: str
    severity: Literal["low", "medium", "high"] = "medium"
    reasons: list[str] = Field(default_factory=list)
    detected_at: datetime = Field(default_factory=utcnow)


class SubstituteRequestMessage(BaseMessage):
    kind: str = "SubstituteRequest"
    task_id: str
    step_id: str
    failed_tool_id: str
    capability: str
    chosen_tool_id: str | None = None
    reason: str = ""


class ListingSubmitMessage(BaseMessage):
    kind: str = "ListingSubmit"
    name: str
    description: str
    spec: dict[str, Any] = Field(default_factory=dict)


class CorrectionSubmitMessage(BaseMessage):
    kind: str = "CorrectionSubmit"
    tool_id: str
    field_name: str
    original_concept: str
    corrected_concept: str
    corrected_unit: str | None = None
    note: str = ""


class MapResultMessage(BaseMessage):
    kind: str = "MapResult"
    tool_id: str
    inputs: list[ConceptSpec] = Field(default_factory=list)
    outputs: list[ConceptSpec] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)
    accepted: bool = True
    staged: bool = False


class RepairRequestMessage(BaseMessage):
    kind: str = "RepairRequest"
    tool_id: str
    violations: list[str] = Field(default_factory=list)
    attempt: int = 1


class SubGoal(BaseModel):
    id: str
    capability: str
    description: str
    intent: str
    slots: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    branch: str = "main"


class LinkCheck(BaseModel):
    source_step: str
    target_step: str
    source_concept: str
    target_concept: str
    source_unit: str | None = None
    target_unit: str | None = None
    concept_ok: bool = True
    units_ok: bool = True
    valid: bool = True
    reason: str = ""


class PlanStep(BaseModel):
    id: str
    subgoal_id: str
    tool_id: str
    tool_name: str
    capability: str
    branch: str = "main"
    input_bindings: dict[str, str] = Field(default_factory=dict)
    params: dict[str, Any] = Field(default_factory=dict)
    link_checks: list[LinkCheck] = Field(default_factory=list)
    status: StepStatus = StepStatus.pending
    output: dict[str, Any] | None = None
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False
    source: str = ""
    substituted_from: str | None = None


class ExecutionPlan(BaseModel):
    plan_id: str = Field(default_factory=lambda: new_id("plan"))
    task_id: str
    steps: list[PlanStep] = Field(default_factory=list)
    branches: dict[str, list[str]] = Field(default_factory=dict)
    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utcnow)


class TraceEvent(BaseModel):
    task_id: str
    seq: int | None = None
    timestamp: datetime = Field(default_factory=utcnow)
    event_type: str
    actor: str
    summary: str
    data: dict[str, Any] = Field(default_factory=dict)


class TaskMetrics(BaseModel):
    total_ms: float = 0.0
    retrieval_ms: float = 0.0
    verification_ms: float = 0.0
    composition_ms: float = 0.0
    execution_ms: float = 0.0
    substitution_ms: float = 0.0
    tokens: int = 0


class TaskResult(BaseModel):
    task_id: str
    task: str
    status: TaskStatus = TaskStatus.completed
    answer: str = ""
    subgoals: list[SubGoal] = Field(default_factory=list)
    candidate_lists: list[CandidateList] = Field(default_factory=list)
    plan: ExecutionPlan | None = None
    trace: list[TraceEvent] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0
    mode: str = "live"
    metrics: TaskMetrics = Field(default_factory=TaskMetrics)
    error: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class CorrectionRequest(BaseModel):
    tool_id: str
    field_name: str
    original_concept: str
    corrected_concept: str
    corrected_unit: str | None = None
    note: str = ""


class CorrectionResult(BaseModel):
    correction_id: str
    accepted: bool
    staged: bool
    violations: list[str] = Field(default_factory=list)
    message: str = ""


class DocumentInfo(BaseModel):
    document_id: str
    name: str
    size_bytes: int
    text_chars: int
    created_at: datetime = Field(default_factory=utcnow)


class ListingIngestRequest(BaseModel):
    name: str
    description: str
    capability: str
    inputs: list[ConceptSpec] = Field(default_factory=list)
    outputs: list[ConceptSpec] = Field(default_factory=list)
    claims: list[ClaimSpec] = Field(default_factory=list)
    docs_url: str = ""


class MonitoringSnapshot(BaseModel):
    trust: list[dict[str, Any]] = Field(default_factory=list)
    breakers: list[dict[str, Any]] = Field(default_factory=list)
    drift_alerts: list[DriftAlertMessage] = Field(default_factory=list)
    providers: list[dict[str, Any]] = Field(default_factory=list)
    mode: str = "live"


class HealthResponse(BaseModel):
    status: str = "ok"
    app: str
    version: str
    mode: str
    tools: int
    llm_enabled: bool
