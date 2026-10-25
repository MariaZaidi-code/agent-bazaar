from __future__ import annotations

import json
from dataclasses import dataclass, field, fields
from enum import Enum
from typing import Any

from .claims import Claim, Evidence
from .enums import (
    ClaimLabel,
    DocStance,
    DriftDetectorKind,
    ProbeOutcome,
    Severity,
    TrustOutcome,
)
from .utils import new_id, utc_now


def _json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    if hasattr(value, "to_dict"):
        return value.to_dict()
    return value


@dataclass(kw_only=True)
class Message:
    sender: str = "unknown"
    correlation_id: str = ""
    id: str = field(default_factory=lambda: new_id())
    timestamp: str = field(default_factory=utc_now)

    @property
    def message_type(self) -> str:
        return self.__class__.__name__

    def to_dict(self) -> dict[str, Any]:
        data = {item.name: _json_value(getattr(self, item.name)) for item in fields(self)}
        data["type"] = self.message_type
        return data

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)


@dataclass
class CoverageReport:
    total_claims: int
    probeable_claims: int
    probed_claims: int
    coverage_percent: float
    probeable_coverage_percent: float = 0.0
    per_tool: dict[str, float] = field(default_factory=dict)
    probe_sources: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_claims": self.total_claims,
            "probeable_claims": self.probeable_claims,
            "probed_claims": self.probed_claims,
            "coverage_percent": self.coverage_percent,
            "probeable_coverage_percent": self.probeable_coverage_percent,
            "per_tool": dict(self.per_tool),
            "probe_sources": dict(self.probe_sources),
            "notes": list(self.notes),
        }


@dataclass
class ClaimAssessment:
    claim: Claim
    label: ClaimLabel
    doc_stance: DocStance
    probe_outcome: ProbeOutcome
    evidence: list[Evidence] = field(default_factory=list)
    rationale: str = ""
    probe_source: str = ""
    probed: bool = False
    probe_error: str = ""
    probe_status_code: int | None = None
    probe_latency_ms: float | None = None
    probe_artifact: str = ""
    probe_checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim.to_dict(),
            "label": self.label.value,
            "doc_stance": self.doc_stance.value,
            "probe_outcome": self.probe_outcome.value,
            "evidence": [item.to_dict() for item in self.evidence],
            "rationale": self.rationale,
            "probe_source": self.probe_source,
            "probed": self.probed,
            "probe_error": self.probe_error,
            "probe_status_code": self.probe_status_code,
            "probe_latency_ms": self.probe_latency_ms,
            "probe_artifact": self.probe_artifact,
            "probe_checks": list(self.probe_checks),
        }


@dataclass(kw_only=True)
class VerifyRequest(Message):
    tool_id: str
    claims: list[Claim] | None = None
    request_all_claims: bool = True
    reprobe_round: int = 0


@dataclass(kw_only=True)
class VerifyResult(Message):
    request_id: str
    tool_id: str
    assessments: list[ClaimAssessment]
    coverage: CoverageReport
    started_at: str
    finished_at: str
    duration_ms: float
    probe_source: str = ""
    notes: list[str] = field(default_factory=list)
    probe_artifact: str = ""
    probe_status_code: int | None = None
    probe_latency_ms: float | None = None
    probe_valid: bool | None = None
    drift_alerts: list[DriftAlert] = field(default_factory=list)

    @property
    def labels(self) -> dict[str, ClaimLabel]:
        return {item.claim.id: item.label for item in self.assessments}


@dataclass(kw_only=True)
class DriftAlert(Message):
    tool_id: str
    field_path: str
    detector: DriftDetectorKind
    old_description: str
    new_sample: Any
    severity: Severity
    distance: float | None = None
    probe_round: int = 0
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class TrustUpdate(Message):
    tool_id: str
    outcome: TrustOutcome
    reason: str
    claim_id: str = ""
    value: float | None = None


@dataclass(kw_only=True)
class Feedback(Message):
    tool_id: str
    outcome: str
    rating: float | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(kw_only=True)
class CorrectionSubmit(Message):
    tool_id: str
    field_path: str
    proposed_concept: str
    proposed_unit: str | None = None
    note: str = ""


@dataclass(kw_only=True)
class RepairRequest(Message):
    tool_id: str
    violations: list[str]
    attempt: int = 1
