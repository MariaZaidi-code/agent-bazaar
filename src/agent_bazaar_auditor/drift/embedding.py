from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..embeddings import EmbeddingModel, HashingEmbedder, cosine_distance, payload_summary
from ..enums import DriftDetectorKind, Severity
from ..messages import DriftAlert
from ..probes.models import ProbeResult
from ..utils import truncate
from .baseline import BaselineRecord, BaselineStore


@dataclass
class EmbeddingCheck:
    tool_id: str
    distance: float | None
    threshold: float
    baseline_created: bool = False
    alert: DriftAlert | None = None
    summary: str = ""
    baseline_summary: str = ""
    notes: list[str] = field(default_factory=list)

    @property
    def detected(self) -> bool:
        return self.alert is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "distance": self.distance,
            "threshold": self.threshold,
            "baseline_created": self.baseline_created,
            "detected": self.detected,
            "alert": self.alert.to_dict() if self.alert else None,
            "summary": self.summary,
            "baseline_summary": self.baseline_summary,
            "notes": list(self.notes),
        }


class EmbeddingDriftDetector:
    def __init__(
        self,
        store: BaselineStore,
        embedder: EmbeddingModel | None = None,
        threshold: float = 0.15,
    ) -> None:
        self.store = store
        self.embedder = embedder or HashingEmbedder()
        self.threshold = float(threshold)

    def establish(self, tool_id: str, payload: Any, probe_round: int = 0) -> BaselineRecord:
        summary = payload_summary(payload)
        record = BaselineRecord(
            tool_id=tool_id,
            summary=summary,
            embedding=self.embedder.embed(summary),
            embedder_name=self.embedder.name,
            dimensions=self.embedder.dimensions,
            probe_round=probe_round,
        )
        self.store.set(record)
        return record

    def check(
        self,
        tool_id: str,
        probe: ProbeResult,
        probe_round: int = 0,
        correlation_id: str = "",
        establish_if_missing: bool = True,
    ) -> EmbeddingCheck:
        if not probe.ok or probe.payload is None:
            return EmbeddingCheck(
                tool_id=tool_id,
                distance=None,
                threshold=self.threshold,
                notes=["Probe failed, so embedding drift was not evaluated."],
            )
        summary = payload_summary(probe.payload)
        current = self.embedder.embed(summary)
        baseline = self.store.get(tool_id, self.embedder.name, self.embedder.dimensions)
        if baseline is None:
            if not establish_if_missing:
                return EmbeddingCheck(
                    tool_id=tool_id,
                    distance=None,
                    threshold=self.threshold,
                    summary=summary,
                    notes=["No baseline exists for this tool and embedder."],
                )
            self.establish(tool_id, probe.payload, probe_round)
            return EmbeddingCheck(
                tool_id=tool_id,
                distance=0.0,
                threshold=self.threshold,
                baseline_created=True,
                summary=summary,
                baseline_summary=summary,
                notes=["Baseline established; no drift alert on the first probe."],
            )
        distance = cosine_distance(current, baseline.embedding)
        alert = None
        if distance > self.threshold:
            severity = Severity.HIGH if distance > self.threshold * 2.0 else Severity.MEDIUM
            alert = DriftAlert(
                sender="auditor",
                correlation_id=correlation_id,
                tool_id=tool_id,
                field_path="response_schema",
                detector=DriftDetectorKind.EMBEDDING,
                old_description=truncate(baseline.summary, 1200),
                new_sample=truncate(probe.payload, 1200),
                severity=severity,
                distance=round(distance, 6),
                probe_round=probe_round,
                details={
                    "threshold": self.threshold,
                    "embedder": self.embedder.name,
                    "baseline_created_at": baseline.created_at,
                    "current_summary": truncate(summary, 1200),
                },
            )
        return EmbeddingCheck(
            tool_id=tool_id,
            distance=distance,
            threshold=self.threshold,
            alert=alert,
            summary=summary,
            baseline_summary=baseline.summary,
        )
