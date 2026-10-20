from __future__ import annotations

from typing import Any

from app.core.trust_registry import TrustRegistry
from app.knowledge.graph import ToolKnowledgeGraph
from app.schemas import (
    Candidate,
    ClaimLabel,
    ClaimVerification,
    DriftAlertMessage,
    VerifyResultMessage,
)

AUDITOR_SENDER = "auditor"


class AuditorStub:
    """Adapter for Qaim's Auditor.

    Seeded claim labels come from tools.json so the interface and Client can be
    developed independently. Replace verify() with the real Auditor's VerifyResult
    implementation without changing the Client.
    """

    def __init__(self, graph: ToolKnowledgeGraph, trust: TrustRegistry) -> None:
        self.graph = graph
        self.trust = trust
        self._drift: dict[str, DriftAlertMessage] = {}

    async def verify(
        self,
        task_id: str,
        subgoal_id: str,
        candidates: list[Candidate],
        correlation_id: str,
    ) -> VerifyResultMessage:
        labels: dict[str, list[ClaimVerification]] = {}
        overall: dict[str, ClaimLabel] = {}
        alerts: list[str] = []
        for candidate in candidates:
            tool = candidate.tool
            tool_labels: list[ClaimVerification] = []
            for claim in tool.claims:
                label = claim.label or ClaimLabel.unsupported
                tool_labels.append(
                    ClaimVerification(
                        tool_id=tool.id,
                        claim=claim.text,
                        label=label,
                        evidence=claim.evidence,
                    )
                )
            labels[tool.id] = tool_labels
            if tool.id in self._drift:
                overall[tool.id] = ClaimLabel.contradicted
                alerts.append(self._drift[tool.id].alert_id)
            elif tool_labels:
                priority = {
                    ClaimLabel.contradicted: 4,
                    ClaimLabel.verified: 3,
                    ClaimLabel.supported: 2,
                    ClaimLabel.unsupported: 1,
                }
                overall[tool.id] = max(tool_labels, key=lambda item: priority[item.label]).label
            else:
                overall[tool.id] = ClaimLabel.unsupported
        return VerifyResultMessage(
            sender=AUDITOR_SENDER,
            recipient="client",
            correlation_id=correlation_id,
            task_id=task_id,
            labels=labels,
            overall=overall,
            drift_alerts=alerts,
        )

    def inject_drift(
        self, tool_id: str, reason: str = "response no longer matches mapping"
    ) -> DriftAlertMessage | None:
        tool = self.graph.get(tool_id)
        if tool is None:
            return None
        alert = DriftAlertMessage(
            sender=AUDITOR_SENDER,
            recipient="client",
            correlation_id=f"drift:{tool_id}",
            tool_id=tool_id,
            provider_id=tool.provider_id,
            severity="high",
            reasons=[reason],
        )
        self._drift[tool_id] = alert
        self.trust.record_contradiction(
            tool.provider_id,
            reason=f"drift detected for {tool_id}: {reason}",
            source="auditor-stub",
        )
        return alert

    def clear_drift(self, tool_id: str) -> bool:
        return self._drift.pop(tool_id, None) is not None

    def alerts(self) -> list[DriftAlertMessage]:
        return list(self._drift.values())

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            {
                "alert_id": alert.alert_id,
                "tool_id": alert.tool_id,
                "provider_id": alert.provider_id,
                "severity": alert.severity,
                "reasons": alert.reasons,
                "detected_at": alert.detected_at.isoformat(),
            }
            for alert in self._drift.values()
        ]

    def reset(self) -> None:
        self._drift.clear()
