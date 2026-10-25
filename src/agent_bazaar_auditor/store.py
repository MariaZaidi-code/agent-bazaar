from __future__ import annotations

from pathlib import Path
from typing import Any

from .claims import Claim, Evidence
from .drift.detector import DriftCheck
from .enums import ClaimLabel
from .messages import ClaimAssessment, DriftAlert, Message, TrustUpdate, VerifyResult
from .probes.models import ProbeResult
from .utils import append_jsonl, atomic_write_json, safe_name, utc_now


class ArtifactStore:
    def __init__(self, root: Path | str = "outputs") -> None:
        self.root = Path(root)
        self.probes_dir = self.root / "probes"
        self.verifications_dir = self.root / "verifications"
        self.reports_dir = self.root / "reports"
        for directory in (self.root, self.probes_dir, self.verifications_dir, self.reports_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def relative(self, path: Path) -> str:
        try:
            return path.relative_to(self.root).as_posix()
        except ValueError:
            return path.as_posix()

    def record_probe(self, probe: ProbeResult, correlation_id: str = "") -> str:
        tool_dir = self.probes_dir / safe_name(probe.tool_id)
        tool_dir.mkdir(parents=True, exist_ok=True)
        stamp = probe.timestamp.replace(":", "-").replace("+", "_")
        path = tool_dir / f"{stamp}.json"
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "correlation_id": correlation_id,
                **probe.to_dict(),
            },
        )
        append_jsonl(
            self.root / "probe_index.jsonl",
            {
                "tool_id": probe.tool_id,
                "timestamp": probe.timestamp,
                "ok": probe.ok,
                "status_code": probe.status_code,
                "source": probe.source.value,
                "artifact": self.relative(path),
                "correlation_id": correlation_id,
            },
        )
        return self.relative(path)

    def record_verification(self, result: VerifyResult) -> str:
        tool_dir = self.verifications_dir / safe_name(result.tool_id)
        tool_dir.mkdir(parents=True, exist_ok=True)
        stamp = result.finished_at.replace(":", "-").replace("+", "_")
        path = tool_dir / f"{stamp}.json"
        atomic_write_json(path, result.to_dict())
        return self.relative(path)

    def record_message(self, message: Message) -> None:
        append_jsonl(self.root / "messages.jsonl", {"logged_at": utc_now(), **message.to_dict()})

    def record_assessment(self, assessment: ClaimAssessment, tool_id: str, correlation_id: str = "") -> None:
        append_jsonl(
            self.root / "knowledge.jsonl",
            {
                "schema_version": 1,
                "logged_at": utc_now(),
                "correlation_id": correlation_id,
                "tool_id": tool_id,
                "claim": assessment.claim.to_dict(),
                "label": assessment.label.value,
                "evidence": [item.to_dict() for item in assessment.evidence],
                "rationale": assessment.rationale,
            },
        )

    def record_claim_evidence(
        self,
        claim: Claim,
        evidence: list[Evidence],
        label: ClaimLabel,
        correlation_id: str = "",
    ) -> None:
        append_jsonl(
            self.root / "graph_writes.jsonl",
            {
                "schema_version": 1,
                "logged_at": utc_now(),
                "correlation_id": correlation_id,
                "tool_id": claim.tool_id,
                "claim": claim.to_dict(),
                "evidence": [item.to_dict() for item in evidence],
                "label": label.value,
            },
        )

    def record_drift(self, check: DriftCheck, correlation_id: str = "") -> None:
        for alert in check.alerts:
            self.record_alert(alert, correlation_id)

    def record_alert(self, alert: DriftAlert, correlation_id: str = "") -> None:
        append_jsonl(
            self.root / "drift_alerts.jsonl",
            {
                "logged_at": utc_now(),
                "correlation_id": correlation_id,
                **alert.to_dict(),
            },
        )

    def record_trust(self, update: TrustUpdate) -> None:
        append_jsonl(self.root / "trust_updates.jsonl", update.to_dict())

    def write_report(self, name: str, content: str) -> Path:
        path = self.reports_dir / safe_name(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.root / name
        atomic_write_json(path, payload)
        return path

    def latest_artifact(self, kind: str) -> str:
        index = self.root / f"{kind}_index.jsonl"
        if not index.exists():
            return ""
        lines = index.read_text(encoding="utf-8").splitlines()
        if not lines:
            return ""
        import json

        return str(json.loads(lines[-1]).get("artifact", ""))
