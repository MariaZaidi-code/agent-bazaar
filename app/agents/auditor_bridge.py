"""Adapter between the application and Qaim's Auditor package.

The Client and the interface were developed against :class:`AuditorStub`, which
returns seeded labels. This module keeps that contract but delegates the six
tools that the Auditor's catalogue can probe to
``agent_bazaar_auditor``. Tools that have no catalogue entry (the local SQL,
document and adversarial weather providers) keep the deterministic seeded
fallback, so the application still works with no network access.

The Auditor is synchronous and keeps mutable probe baselines and artifact
stores, so every call is serialised through one lock and executed in a worker
thread from the async Client.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from agent_bazaar_auditor.auditor import Auditor as CatalogAuditor
from agent_bazaar_auditor.config import Settings as AuditorSettings
from agent_bazaar_auditor.enums import Severity as AuditorSeverity
from agent_bazaar_auditor.mocks.registry import MockRegistry
from agent_bazaar_auditor.utils import stable_id
from app.agents.auditor_stub import AuditorStub
from app.core.trust_registry import TrustRegistry
from app.knowledge.graph import ToolKnowledgeGraph
from app.schemas import (
    Candidate,
    ClaimLabel,
    ClaimVerification,
    DriftAlertMessage,
    VerifyResultMessage,
    utcnow,
)

# Application tool id -> Auditor catalogue id. The app uses provider-specific
# ids while the Auditor catalogue uses the public API name.
TOOL_ALIASES: dict[str, str] = {
    "open-meteo-forecast": "open-meteo",
    "frankfurter-currency": "frankfurter",
    "nominatim-geocode": "nominatim",
    "restcountries-facts": "rest-countries",
    "nager-holidays": "nager-date",
    "arxiv-search": "arxiv",
}

_SEVERITY_MAP = {
    AuditorSeverity.LOW: "low",
    AuditorSeverity.MEDIUM: "medium",
    AuditorSeverity.HIGH: "high",
    AuditorSeverity.CRITICAL: "high",
}
_LABEL_MAP = {
    "Verified": ClaimLabel.verified,
    "Supported": ClaimLabel.supported,
    "Contradicted": ClaimLabel.contradicted,
    "Unsupported": ClaimLabel.unsupported,
}


class AuditorBridge:
    """Qaim's Auditor behind the application's Auditor contract."""

    def __init__(
        self,
        graph: ToolKnowledgeGraph,
        trust: TrustRegistry,
        runtime_dir: Path,
        *,
        live: bool = False,
        persist: bool = True,
    ) -> None:
        self.graph = graph
        self.trust = trust
        self.live = live
        self._fallback = AuditorStub(graph, trust)
        self._lock = threading.Lock()
        self._alerts: dict[str, DriftAlertMessage] = {}
        auditor_settings = AuditorSettings(
            outputs_dir=runtime_dir / "outputs",
            cache_dir=runtime_dir / "cache",
            live=live,
            drift_mode="full",
        ).prepare()
        self.auditor = CatalogAuditor(settings=auditor_settings, persist=persist)
        self.mocks = MockRegistry(
            self.auditor.harness,
            catalog=self.auditor.catalog,
            definitions=self.auditor.definitions,
        )

    # -- helpers ---------------------------------------------------------
    def catalog_tool_id(self, tool_id: str) -> str | None:
        return TOOL_ALIASES.get(tool_id)

    def _app_tool_id(self, catalog_tool_id: str) -> str | None:
        for app_id, catalog_id in TOOL_ALIASES.items():
            if catalog_id == catalog_tool_id:
                return app_id
        return None

    def _overall(self, labels: list[str]) -> ClaimLabel:
        if "Contradicted" in labels:
            return ClaimLabel.contradicted
        if labels and all(label == "Verified" for label in labels):
            return ClaimLabel.verified
        if any(label in {"Verified", "Supported"} for label in labels):
            return ClaimLabel.supported
        return ClaimLabel.unsupported

    def _evidence(self, assessment: Any) -> str:
        pieces: list[str] = []
        if assessment.rationale:
            pieces.append(str(assessment.rationale))
        for evidence in assessment.evidence:
            summary = str(evidence.summary or "").strip()
            if summary and summary not in pieces:
                pieces.append(summary)
        return "; ".join(pieces)[:600]

    def _convert_alert(
        self,
        alert: Any,
        tool_id: str,
        correlation_id: str,
        reason: str = "",
    ) -> DriftAlertMessage:
        tool = self.graph.get(tool_id)
        provider_id = tool.provider_id if tool is not None else "unknown"
        message = ""
        if isinstance(alert.details, dict):
            message = str(alert.details.get("message") or "").strip()
        if not message:
            detector = getattr(alert.detector, "value", str(alert.detector))
            field = alert.field_path or "response"
            message = f"{detector} drift detected on {field}."
        reasons = [reason] if reason else []
        if message not in reasons:
            reasons.append(message)
        try:
            detected_at = datetime.fromisoformat(str(alert.timestamp))
        except (TypeError, ValueError):
            detected_at = utcnow()
        if detected_at.tzinfo is None:
            detected_at = detected_at.replace(tzinfo=UTC)
        return DriftAlertMessage(
            sender="auditor",
            recipient="client",
            correlation_id=correlation_id or f"auditor:{tool_id}",
            alert_id=f"drift_{stable_id(alert.tool_id, alert.field_path, alert.detector.value, message)}",
            tool_id=tool_id,
            provider_id=provider_id,
            severity=_SEVERITY_MAP.get(alert.severity, "medium"),
            reasons=reasons,
            detected_at=detected_at,
        )

    def _store_alerts(
        self,
        alerts: list[Any],
        tool_id: str,
        correlation_id: str,
        reason: str = "",
    ) -> list[DriftAlertMessage]:
        converted: list[DriftAlertMessage] = []
        for alert in alerts:
            item = self._convert_alert(alert, tool_id, correlation_id, reason=reason)
            is_new = item.alert_id not in self._alerts
            self._alerts[item.alert_id] = item
            converted.append(item)
            if is_new:
                self.trust.record_contradiction(
                    item.provider_id,
                    reason=f"Auditor {item.severity} drift on {tool_id}: "
                    + "; ".join(item.reasons),
                    source="auditor",
                )
        return converted

    def _verify_catalog(
        self,
        candidates: list[Candidate],
        correlation_id: str,
    ) -> dict[str, tuple[list[ClaimVerification], ClaimLabel, list[DriftAlertMessage]]]:
        results: dict[str, tuple[list[ClaimVerification], ClaimLabel, list[DriftAlertMessage]]] = {}
        with self._lock:
            for candidate in candidates:
                catalog_id = TOOL_ALIASES[candidate.tool.id]
                verification = self.auditor.verify(
                    catalog_id,
                    correlation_id=correlation_id,
                    establish_baseline=True,
                )
                labels = [
                    ClaimVerification(
                        tool_id=candidate.tool.id,
                        claim=assessment.claim.text,
                        label=_LABEL_MAP.get(assessment.label.value, ClaimLabel.unsupported),
                        evidence=self._evidence(assessment),
                    )
                    for assessment in verification.assessments
                ]
                overall = self._overall([item.label.value for item in verification.assessments])
                alerts = self._store_alerts(
                    verification.drift_alerts,
                    candidate.tool.id,
                    correlation_id,
                    reason="Auditor re-probe found response drift.",
                )
                results[candidate.tool.id] = (labels, overall, alerts)
        return results

    # -- Auditor contract ------------------------------------------------
    async def verify(
        self,
        task_id: str,
        subgoal_id: str,
        candidates: list[Candidate],
        correlation_id: str,
    ) -> VerifyResultMessage:
        catalog_candidates = [
            candidate for candidate in candidates if candidate.tool.id in TOOL_ALIASES
        ]
        fallback_candidates = [
            candidate for candidate in candidates if candidate.tool.id not in TOOL_ALIASES
        ]
        result = VerifyResultMessage(
            sender="auditor",
            recipient="client",
            correlation_id=correlation_id,
            task_id=task_id,
        )
        if catalog_candidates:
            catalog_results = await asyncio.to_thread(
                self._verify_catalog, catalog_candidates, correlation_id
            )
            for tool_id, (labels, overall, alerts) in catalog_results.items():
                result.labels[tool_id] = labels
                result.overall[tool_id] = overall
                result.drift_alerts.extend(alert.alert_id for alert in alerts)
        if fallback_candidates:
            fallback = await self._fallback.verify(
                task_id, subgoal_id, fallback_candidates, correlation_id
            )
            result.labels.update(fallback.labels)
            result.overall.update(fallback.overall)
            result.drift_alerts.extend(fallback.drift_alerts)
        return result

    def inject_drift(
        self,
        tool_id: str,
        reason: str = "response no longer matches mapping",
    ) -> DriftAlertMessage | None:
        catalog_id = TOOL_ALIASES.get(tool_id)
        if catalog_id is None:
            return self._fallback.inject_drift(tool_id, reason=reason)
        if self.graph.get(tool_id) is None:
            return None
        with self._lock:
            # Establish the healthy baseline before changing the mock response.
            self.auditor.verify(catalog_id, establish_baseline=True)
            self.mocks.control(catalog_id, "rename_field")
            try:
                verification = self.auditor.monitor_tool(
                    catalog_id,
                    probe_round=1,
                    establish_baseline=False,
                )
            finally:
                self.mocks.remove(catalog_id)
            alerts = self._store_alerts(
                verification.drift_alerts,
                tool_id,
                f"demo:drift:{tool_id}",
                reason=reason,
            )
            if alerts:
                return alerts[0]
        # A provider whose fixture cannot drift falls back to the documented
        # demo injection instead of returning a misleading empty result.
        return self._fallback.inject_drift(tool_id, reason=reason)

    def clear_drift(self, tool_id: str) -> bool:
        catalog_id = TOOL_ALIASES.get(tool_id)
        removed = self._fallback.clear_drift(tool_id)
        for alert_id, alert in list(self._alerts.items()):
            if alert.tool_id == tool_id:
                self._alerts.pop(alert_id, None)
                removed = True
        if catalog_id is not None:
            with self._lock:
                self.auditor.monitor.reset(catalog_id)
        return removed

    def alerts(self) -> list[DriftAlertMessage]:
        combined = {alert.alert_id: alert for alert in self._fallback.alerts()}
        combined.update(self._alerts)
        return list(combined.values())

    def snapshot(self) -> list[dict[str, Any]]:
        return [
            alert.model_dump(mode="json")
            for alert in self.alerts()
        ]

    def reset(self) -> None:
        self._fallback.reset()
        self._alerts.clear()
        with self._lock:
            self.mocks.reset_all()
            self.auditor.monitor.reset_all()
            self.auditor.trust_ledger.tools.clear()
            self.auditor.trust_ledger.history.clear()
            self.auditor.trust_ledger.save()
            self.auditor.trust_feed.updates.clear()

    # -- Interface-facing operations ------------------------------------
    def overview(self) -> dict[str, Any]:
        mappings = [
            {
                "app_tool_id": app_id,
                "catalog_tool_id": catalog_id,
                "provider_id": (
                    self.graph.get(app_id).provider_id
                    if self.graph.get(app_id) is not None
                    else ""
                ),
            }
            for app_id, catalog_id in TOOL_ALIASES.items()
        ]
        return {
            "available": True,
            "mode": "live" if self.live else "fixture",
            "catalog_tools": len(self.auditor.catalog),
            "probe_definitions": len(self.auditor.definitions),
            "mappings": mappings,
            "tools": [
                {
                    **tool.to_dict(),
                    "app_tool_id": self._app_tool_id(tool.tool_id) or "",
                    "probeable": tool.tool_id in self.auditor.definitions,
                }
                for tool in self.auditor.catalog.values()
            ],
            "trust": self.auditor.trust_snapshot(),
            "feed": self.auditor.trust_feed.summary(),
        }

    def verify_tool(self, tool_id: str, *, force_live: bool = False) -> dict[str, Any]:
        catalog_id = TOOL_ALIASES.get(tool_id)
        if catalog_id is None:
            raise KeyError(f"Auditor has no catalogue entry for {tool_id}")
        with self._lock:
            result = self.auditor.verify(
                catalog_id,
                correlation_id=f"interface:verify:{tool_id}",
                force_live=force_live,
                establish_baseline=True,
            )
            alerts = self._store_alerts(
                result.drift_alerts,
                tool_id,
                f"interface:verify:{tool_id}",
                reason="Auditor verification found response drift.",
            )
        payload = result.to_dict()
        payload["app_tool_id"] = tool_id
        payload["app_labels"] = [
            {
                "claim": assessment.claim.text,
                "label": _LABEL_MAP.get(assessment.label.value, ClaimLabel.unsupported).value,
                "evidence": self._evidence(assessment),
            }
            for assessment in result.assessments
        ]
        payload["app_overall"] = self._overall(
            [assessment.label.value for assessment in result.assessments]
        ).value
        payload["alerts"] = [alert.model_dump(mode="json") for alert in alerts]
        return payload

    def monitor_tool(
        self,
        tool_id: str,
        *,
        force_live: bool = False,
        establish_baseline: bool = False,
    ) -> dict[str, Any]:
        catalog_id = TOOL_ALIASES.get(tool_id)
        if catalog_id is None:
            raise KeyError(f"Auditor has no catalogue entry for {tool_id}")
        with self._lock:
            result = self.auditor.monitor_tool(
                catalog_id,
                force_live=force_live,
                establish_baseline=establish_baseline,
            )
            alerts = self._store_alerts(
                result.drift_alerts,
                tool_id,
                f"interface:monitor:{tool_id}",
                reason="Interface monitoring found response drift.",
            )
        payload = result.to_dict()
        payload["app_tool_id"] = tool_id
        payload["alerts"] = [alert.model_dump(mode="json") for alert in alerts]
        return payload

    def trust_payload(self) -> dict[str, Any]:
        return {
            "leaderboard": self.auditor.trust_snapshot(),
            "feed": self.auditor.trust_feed.summary(),
        }

    def status(self) -> dict[str, Any]:
        return {
            "available": True,
            "mode": "live" if self.live else "fixture",
            "catalog_tools": len(self.auditor.catalog),
            "mapped_tools": len(TOOL_ALIASES),
            "alerts": len(self.alerts()),
            "trust_observations": sum(
                entry.observations for entry in self.auditor.trust_ledger.tools.values()
            ),
        }
