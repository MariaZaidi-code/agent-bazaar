"""Structured JSON message protocol shared by all four agents.

Every message carries an id, a timestamp, the sender and a correlation id so the
trace viewer can follow a task end to end (Proposal v1.3 Sections 5.2 and 5.5).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentRole(StrEnum):
    MAPPER = "mapper"
    AUDITOR = "auditor"
    CLIENT = "client"
    PROVIDER = "provider"
    DEVELOPER = "developer"
    SYSTEM = "system"


class FieldMappingStatus(StrEnum):
    MAPPED = "mapped"
    REPAIRED = "repaired"
    DRIFT_REMAPPED = "drift_remapped"
    UNMAPPED = "unmapped"
    PENDING_REVIEW = "pending_review"


class MessageBase(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    sender: AgentRole = AgentRole.SYSTEM
    correlation_id: str = Field(default_factory=lambda: uuid.uuid4().hex)

    @property
    def message_type(self) -> str:
        return type(self).__name__


def new_message(model: type[MessageBase], **kwargs: Any) -> Any:
    if "id" not in kwargs:
        kwargs["id"] = uuid.uuid4().hex
    if "timestamp" not in kwargs:
        kwargs["timestamp"] = datetime.now(UTC)
    return model(**kwargs)


class FieldSpec(BaseModel):
    """A single field extracted from a listing, before mapping."""

    model_config = ConfigDict(extra="allow")

    field_path: str
    name: str = ""
    type: str = "string"
    description: str = ""
    sample_value: Any = None
    direction: Literal["input", "output"] = "output"
    endpoint: str | None = None
    method: str | None = None
    required: bool | None = None


class FieldMapping(BaseModel):
    model_config = ConfigDict(extra="allow")

    field_path: str
    concept: str = ""
    concept_label: str = ""
    unit: str | None = None
    unit_family: str | None = None
    confidence: float = 0.0
    reason: str = ""
    status: FieldMappingStatus = FieldMappingStatus.MAPPED
    attempts: int = 0
    source: Literal["llm", "correction", "rule", "fallback", "drift"] = "llm"


class ListingSubmit(MessageBase):
    tool_id: str
    source: str
    spec_format: Literal["auto", "openapi_json", "openapi_yaml", "pdf", "docx", "text"] = "auto"
    provider_id: str | None = None
    provider_name: str | None = None
    base_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MapRequest(MessageBase):
    tool_id: str
    fields: list[FieldSpec] = Field(default_factory=list)
    options: dict[str, Any] = Field(default_factory=dict)


class MapResult(MessageBase):
    tool_id: str
    mappings: list[FieldMapping] = Field(default_factory=list)
    unmapped: list[FieldSpec] = Field(default_factory=list)
    stats: dict[str, Any] = Field(default_factory=dict)


class CorrectionSubmit(MessageBase):
    tool_id: str
    field_path: str
    corrected_concept: str
    corrected_unit: str | None = None
    note: str = ""
    submitted_by: str = ""


class RepairRequest(MessageBase):
    tool_id: str
    field_path: str
    violation_message: str
    rejected_mapping: FieldMapping | None = None
    attempt: int = 0


class DriftAlert(MessageBase):
    tool_id: str
    field_path: str
    old_description: str = ""
    new_sample: Any = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    detected_by: str = "auditor"


class Feedback(MessageBase):
    tool_id: str
    outcome: str
    rating: float | None = None
    field_path: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class TrustUpdate(MessageBase):
    tool_id: str
    outcome: Literal[
        "probe_pass",
        "probe_fail",
        "call_success",
        "call_failure",
        "schema_valid",
        "schema_invalid",
        "rating",
    ]
    weight: float = 1.0
    details: dict[str, Any] = Field(default_factory=dict)


class TaskRequest(MessageBase):
    task: str
    constraints: dict[str, Any] = Field(default_factory=dict)


class CandidateList(MessageBase):
    task: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)


class VerifyRequest(MessageBase):
    tool_id: str
    claims: list[str] = Field(default_factory=list)


class VerifyResult(MessageBase):
    tool_id: str
    labels: list[dict[str, Any]] = Field(default_factory=list)


class ServiceOffer(MessageBase):
    tool_id: str
    capability: str
    price: float | None = None


class ServiceCall(MessageBase):
    tool_id: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ServiceResult(MessageBase):
    tool_id: str
    success: bool
    payload: Any = None
    error: str | None = None


class SubstituteRequest(MessageBase):
    tool_id: str
    required_input: str | None = None
    required_output: str | None = None
    reason: str = ""
