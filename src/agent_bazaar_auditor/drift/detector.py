from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..embeddings import EmbeddingModel
from ..messages import DriftAlert
from ..probes.definitions import ProbeDefinition
from ..probes.models import ProbeResult
from .baseline import BaselineStore
from .embedding import EmbeddingCheck, EmbeddingDriftDetector
from .rules import RuleBasedDriftDetector


@dataclass
class DriftCheck:
    tool_id: str
    mode: str
    threshold: float
    alerts: list[DriftAlert] = field(default_factory=list)
    rule_alerts: list[DriftAlert] = field(default_factory=list)
    embedding_alerts: list[DriftAlert] = field(default_factory=list)
    embedding: EmbeddingCheck | None = None
    baseline_created: bool = False

    @property
    def detected(self) -> bool:
        return bool(self.alerts)

    @property
    def distance(self) -> float | None:
        return self.embedding.distance if self.embedding else None

    @property
    def detectors(self) -> list[str]:
        values: list[str] = []
        if self.rule_alerts:
            values.append("rule")
        if self.embedding_alerts:
            values.append("embedding")
        return values

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "mode": self.mode,
            "threshold": self.threshold,
            "detected": self.detected,
            "detectors": self.detectors,
            "distance": self.distance,
            "baseline_created": self.baseline_created,
            "alerts": [alert.to_dict() for alert in self.alerts],
            "rule_alerts": [alert.to_dict() for alert in self.rule_alerts],
            "embedding_alerts": [alert.to_dict() for alert in self.embedding_alerts],
            "embedding": self.embedding.to_dict() if self.embedding else None,
        }


class DriftMonitor:
    def __init__(
        self,
        store: BaselineStore,
        embedder: EmbeddingModel | None = None,
        threshold: float = 0.15,
        mode: str = "full",
        rule_detector: RuleBasedDriftDetector | None = None,
    ) -> None:
        if mode not in {"full", "rule_only", "embedding_only"}:
            raise ValueError("mode must be full, rule_only or embedding_only")
        self.store = store
        self.mode = mode
        self.rule_detector = rule_detector or RuleBasedDriftDetector()
        self.embedding_detector = EmbeddingDriftDetector(store, embedder=embedder, threshold=threshold)

    @property
    def threshold(self) -> float:
        return self.embedding_detector.threshold

    @threshold.setter
    def threshold(self, value: float) -> None:
        self.embedding_detector.threshold = float(value)

    def check(
        self,
        tool_id: str,
        probe: ProbeResult,
        definition: ProbeDefinition,
        probe_round: int = 1,
        correlation_id: str = "",
        establish_if_missing: bool = True,
    ) -> DriftCheck:
        rule_alerts: list[DriftAlert] = []
        embedding_check: EmbeddingCheck | None = None
        embedding_alerts: list[DriftAlert] = []
        if self.mode in {"full", "rule_only"}:
            rule_alerts = self.rule_detector.check(tool_id, probe, definition, probe_round, correlation_id)
        if self.mode in {"full", "embedding_only"}:
            embedding_check = self.embedding_detector.check(
                tool_id,
                probe,
                probe_round=probe_round,
                correlation_id=correlation_id,
                establish_if_missing=establish_if_missing,
            )
            if embedding_check.alert is not None:
                embedding_alerts.append(embedding_check.alert)
        alerts = [*rule_alerts, *embedding_alerts]
        return DriftCheck(
            tool_id=tool_id,
            mode=self.mode,
            threshold=self.threshold,
            alerts=alerts,
            rule_alerts=rule_alerts,
            embedding_alerts=embedding_alerts,
            embedding=embedding_check,
            baseline_created=bool(embedding_check and embedding_check.baseline_created),
        )

    def reset(self, tool_id: str) -> None:
        self.store.clear(tool_id)

    def reset_all(self) -> None:
        self.store.clear_all()
