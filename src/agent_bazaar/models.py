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


class ToolSummary(BaseModel):
    tool_id: str
    iri: str = ""
    name: str = ""
    capabilities: list[str] = Field(default_factory=list)
    provider_id: str = ""
    trust: float | None = None
    score: float | None = None
    reason: str = ""
