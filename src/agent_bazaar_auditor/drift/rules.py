from __future__ import annotations

import difflib
from dataclasses import dataclass, field
from typing import Any

from ..enums import DriftDetectorKind, Severity
from ..messages import DriftAlert
from ..probes.definitions import FieldSpec, ProbeDefinition
from ..probes.models import MISSING, ProbeResult, resolve_path
from ..utils import truncate


@dataclass
class DriftFinding:
    field_path: str
    kind: str
    message: str
    severity: Severity
    old_description: str = ""
    new_sample: Any = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_alert(self, tool_id: str, probe_round: int = 0, correlation_id: str = "") -> DriftAlert:
        return DriftAlert(
            sender="auditor",
            correlation_id=correlation_id,
            tool_id=tool_id,
            field_path=self.field_path,
            detector=DriftDetectorKind.RULE,
            old_description=self.old_description,
            new_sample=truncate(self.new_sample),
            severity=self.severity,
            probe_round=probe_round,
            details={"kind": self.kind, "message": self.message, **self.details},
        )


def _describe_field(path: str, spec: FieldSpec) -> str:
    unit = f", unit {spec.unit}" if spec.unit else ""
    range_text = ""
    if spec.minimum is not None or spec.maximum is not None:
        range_text = f", range [{spec.minimum}, {spec.maximum}]"
    return f"{path}: {spec.expected_type}{unit}{range_text}"


def leaf_paths(payload: Any, prefix: str = "") -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, (dict, list)):
                items.extend(leaf_paths(value, path))
            else:
                items.append((path, value))
    elif isinstance(payload, list):
        for value in payload[:6]:
            if isinstance(value, (dict, list)):
                items.extend(leaf_paths(value, prefix))
            elif prefix:
                items.append((prefix, value))
    return items


def _rename_candidate(missing_path: str, payload: Any, expected_paths: set[str]) -> tuple[str, Any] | None:
    missing_leaf = missing_path.split(".")[-1]
    best: tuple[float, str, Any] | None = None
    for path, value in leaf_paths(payload):
        if path in expected_paths:
            continue
        leaf = path.split(".")[-1]
        score = difflib.SequenceMatcher(None, missing_leaf.lower(), leaf.lower()).ratio()
        if best is None or score > best[0]:
            best = (score, path, value)
    if best is not None and best[0] >= 0.55:
        return best[1], best[2]
    return None


class RuleBasedDriftDetector:
    def __init__(self, rename_similarity: float = 0.55) -> None:
        self.rename_similarity = rename_similarity

    def check(
        self,
        tool_id: str,
        probe: ProbeResult,
        definition: ProbeDefinition,
        probe_round: int = 0,
        correlation_id: str = "",
    ) -> list[DriftAlert]:
        findings: list[DriftFinding] = []
        if not probe.ok:
            severity = Severity.CRITICAL if probe.status_code >= 500 or probe.status_code == 0 else Severity.HIGH
            findings.append(
                DriftFinding(
                    field_path="",
                    kind="transport",
                    message=probe.error or f"Probe failed with HTTP {probe.status_code}.",
                    severity=severity,
                    old_description="Probe was expected to return a usable HTTP 2xx response.",
                    new_sample={"status_code": probe.status_code, "error": probe.error},
                    details={"status_code": probe.status_code, "probe_source": probe.source.value},
                )
            )
        else:
            for path, spec in definition.expected_fields.items():
                value = resolve_path(probe.payload, path)
                if value is MISSING:
                    if spec.required:
                        candidate = _rename_candidate(path, probe.payload, set(definition.expected_fields))
                        if candidate is not None:
                            candidate_path, candidate_value = candidate
                            findings.append(
                                DriftFinding(
                                    field_path=path,
                                    kind="renamed_field",
                                    message=f"Mapped field {path} is missing; {candidate_path} looks like a rename.",
                                    severity=Severity.HIGH,
                                    old_description=_describe_field(path, spec),
                                    new_sample=candidate_value,
                                    details={"candidate_path": candidate_path},
                                )
                            )
                        else:
                            findings.append(
                                DriftFinding(
                                    field_path=path,
                                    kind="missing_field",
                                    message=f"Mapped field {path} is missing.",
                                    severity=Severity.HIGH,
                                    old_description=_describe_field(path, spec),
                                    new_sample=None,
                                )
                            )
                    continue
                if spec.expected_type not in {"any", "present"} and not _type_matches(value, spec.expected_type):
                    findings.append(
                        DriftFinding(
                            field_path=path,
                            kind="type_changed",
                            message=f"Mapped field {path} changed type from {spec.expected_type} to {type(value).__name__}.",
                            severity=Severity.HIGH,
                            old_description=_describe_field(path, spec),
                            new_sample=value,
                        )
                    )
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    if spec.minimum is not None and value < spec.minimum:
                        findings.append(
                            DriftFinding(
                                field_path=path,
                                kind="out_of_range",
                                message=f"Value at {path} is below the mapped plausible range.",
                                severity=Severity.MEDIUM,
                                old_description=_describe_field(path, spec),
                                new_sample=value,
                            )
                        )
                    if spec.maximum is not None and value > spec.maximum:
                        findings.append(
                            DriftFinding(
                                field_path=path,
                                kind="out_of_range",
                                message=f"Value at {path} is above the mapped plausible range.",
                                severity=Severity.MEDIUM,
                                old_description=_describe_field(path, spec),
                                new_sample=value,
                            )
                        )
                if spec.unit:
                    unit_path = definition.unit_paths.get(path)
                    if unit_path:
                        unit_value = resolve_path(probe.payload, unit_path)
                        if unit_value is MISSING:
                            findings.append(
                                DriftFinding(
                                    field_path=unit_path,
                                    kind="missing_unit",
                                    message=f"Mapped unit field {unit_path} is missing.",
                                    severity=Severity.HIGH,
                                    old_description=f"{unit_path}: string, unit {spec.unit}",
                                    new_sample=None,
                                )
                            )
                        elif _normalize_unit(unit_value) != _normalize_unit(spec.unit):
                            findings.append(
                                DriftFinding(
                                    field_path=path,
                                    kind="unit_changed",
                                    message=f"Unit at {unit_path} is {unit_value}, expected {spec.unit}.",
                                    severity=Severity.HIGH,
                                    old_description=_describe_field(path, spec),
                                    new_sample=value,
                                    details={"unit_path": unit_path, "observed_unit": unit_value},
                                )
                            )
            required_parameters = probe.metadata.get("required_parameters")
            if required_parameters:
                allowed = set(definition.params) | set(definition.safe_input)
                unexpected = [parameter for parameter in required_parameters if parameter not in allowed]
                if unexpected:
                    findings.append(
                        DriftFinding(
                            field_path="parameters",
                            kind="new_required_parameter",
                            message=f"Probe reported new required parameters: {', '.join(unexpected)}.",
                            severity=Severity.HIGH,
                            old_description="No new required request parameters were mapped.",
                            new_sample=unexpected,
                        )
                    )
        deduplicated: list[DriftFinding] = []
        seen: set[tuple[str, str]] = set()
        for finding in findings:
            key = (finding.field_path, finding.kind)
            if key not in seen:
                seen.add(key)
                deduplicated.append(finding)
        return [finding.to_alert(tool_id, probe_round, correlation_id) for finding in deduplicated]


def _type_matches(value: Any, expected: str) -> bool:
    if expected in {"any", "present", "xml"}:
        return value is not None
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "string":
        return isinstance(value, str)
    if expected == "array":
        return isinstance(value, list)
    if expected == "object":
        return isinstance(value, dict)
    if expected == "boolean":
        return isinstance(value, bool)
    return True


def _normalize_unit(value: Any) -> str:
    text = str(value).strip().lower().replace("°", "").replace("degrees", "").strip()
    if "/" in text:
        text = text.split("/", 1)[0].strip()
    return {
        "c": "celsius",
        "celsius": "celsius",
        "f": "fahrenheit",
        "fahrenheit": "fahrenheit",
        "kelvin": "kelvin",
        "k": "kelvin",
        "km": "km",
        "kilometre": "km",
        "kilometer": "km",
        "m": "m",
        "usd": "usd",
        "pkr": "pkr",
    }.get(text, text)
