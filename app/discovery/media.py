"""Media types for the discovery API.

These define the response shapes for the discovery endpoints,
following the project's convention of explicit response models.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DiscoveryProviderSummary(BaseModel):
    """Summary of a discovered/staged/verified/suspended provider."""

    tool_id: str
    name: str
    provider_id: str
    state: str
    capabilities: list[str] = Field(default_factory=list)
    base_url: str = ""
    discovered_at: float = 0.0
    staged_at: float | None = None
    verified_at: float | None = None
    suspended_reason: str | None = None
    duplicate_of: str | None = None
    endpoint_count: int = 0
    field_count: int = 0
    verification_notes: list[str] = Field(default_factory=list)


class DiscoveryStats(BaseModel):
    """Statistics for the discovery registry."""

    total: int = 0
    discovered: int = 0
    staged: int = 0
    verified: int = 0
    suspended: int = 0
    capabilities: list[str] = Field(default_factory=list)


class DiscoveryRunResult(BaseModel):
    """Result of a discovery run."""

    discovered: int = 0
    providers: list[DiscoveryProviderSummary] = Field(default_factory=list)


class DiscoveryBatchResult(BaseModel):
    """Result of a batch state transition."""

    count: int = 0
    providers: list[DiscoveryProviderSummary] = Field(default_factory=list)


class DiscoveryResetResult(BaseModel):
    """Result of a registry reset."""

    cleared: int = 0


class DiscoveryExportResult(BaseModel):
    """Result of an export."""

    exported: str = ""
    providers: dict[str, int] = Field(default_factory=dict)


class DiscoveryImportResult(BaseModel):
    """Result of an import."""

    imported: int = 0
