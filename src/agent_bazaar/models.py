"""Shared domain models used across the knowledge layer modules."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ConceptInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    iri: str
    label: str
    data_type: str = "string"
    unit_family: str | None = None
    unit: str | None = None
    unit_bearing: bool = False
    parents: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    definition: str = ""


class ProviderRecord(BaseModel):
    provider_id: str
    name: str = ""
    homepage: str = ""


class ClaimRecord(BaseModel):
    claim_id: str
    text: str
    source: str = ""


class MappedField(BaseModel):
    model_config = ConfigDict(extra="allow")

    field_path: str
    name: str = ""
    concept: str
    concept_label: str = ""
    unit: str | None = None
    unit_family: str | None = None
    data_type: str = "string"
    direction: Literal["input", "output"] = "output"
    confidence: float = 0.0
    reason: str = ""
    status: str = "mapped"


class ToolRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    tool_id: str
    name: str = ""
    description: str = ""
    provider_id: str = ""
    provider_name: str = ""
    base_url: str = ""
    capabilities: list[str] = Field(default_factory=list)
    inputs: list[MappedField] = Field(default_factory=list)
    outputs: list[MappedField] = Field(default_factory=list)
    claims: list[ClaimRecord] = Field(default_factory=list)
    trust: float | None = None
    source: str = ""
    version: str = ""
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)
    pricing_tier: str = "unknown"
    access_requirement: str = "unknown"
    price_amount: float | None = None
    price_currency: str = ""
    rate_limit_policy: str = ""
    probe_budget_per_minute: int | None = None
    licence: str = ""
    terms_url: str = ""
    doc_quality: float = 0.0
    doc_sub_scores: dict[str, float] = Field(default_factory=dict)
    tier_evidence: list[str] = Field(default_factory=list)
    access_evidence: list[str] = Field(default_factory=list)


class ToolQualityProfile(BaseModel):
    """Commercial, access, reputation and documentation facts of one tool.

    These are facts, not policy: the Client decides how to weigh them.
    """

    model_config = ConfigDict(extra="allow")

    tool_id: str
    pricing_tier: str = "unknown"
    access_requirement: str = "unknown"
    price_amount: float | None = None
    price_currency: str = ""
    rate_limit_policy: str = ""
    probe_budget_per_minute: int | None = None
    rating_value: float | None = None
    rating_count: int = 0
    rating_confidence: float = 0.0
    doc_quality: float = 0.0
    doc_sub_scores: dict[str, float] = Field(default_factory=dict)
    mapping_coverage: float = 0.0
    licence: str = ""
    terms_url: str = ""
    is_executable: bool = False
    tier_evidence: list[str] = Field(default_factory=list)
    access_evidence: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)


class ToolSummary(BaseModel):
    tool_id: str
    iri: str = ""
    name: str = ""
    capabilities: list[str] = Field(default_factory=list)
    provider_id: str = ""
    trust: float | None = None
    score: float | None = None
    reason: str = ""
    pricing_tier: str = "unknown"
    access_requirement: str = "unknown"
    rating_value: float | None = None
    rating_count: int = 0
    doc_quality: float = 0.0
    mapping_coverage: float = 0.0
    is_executable: bool = False
    licence: str = ""
