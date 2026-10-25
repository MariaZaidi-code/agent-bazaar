from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..enums import ProbeOutcome, ProbeSource
from ..utils import utc_now


@dataclass
class ProbeResult:
    tool_id: str
    ok: bool
    status_code: int
    payload: Any
    source: ProbeSource
    raw_text: str = ""
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=utc_now)
    error: str = ""
    url: str = ""
    cached: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "ok": self.ok,
            "status_code": self.status_code,
            "payload": self.payload,
            "source": self.source.value,
            "raw_text": self.raw_text,
            "latency_ms": self.latency_ms,
            "timestamp": self.timestamp,
            "error": self.error,
            "url": self.url,
            "cached": self.cached,
            "metadata": dict(self.metadata),
        }


@dataclass
class ValidationIssue:
    path: str
    message: str
    expected: str = ""
    actual: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }


@dataclass
class PayloadValidation:
    ok: bool
    issues: list[ValidationIssue] = field(default_factory=list)
    checked_fields: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "issues": [issue.to_dict() for issue in self.issues],
            "checked_fields": self.checked_fields,
        }


@dataclass
class ClaimProbeCheck:
    outcome: ProbeOutcome
    reason: str
    field_path: str = ""
    actual_value: Any = None
    expected: str = ""
    checks: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "outcome": self.outcome.value,
            "reason": self.reason,
            "field_path": self.field_path,
            "actual_value": self.actual_value,
            "expected": self.expected,
            "checks": list(self.checks),
        }


MISSING = object()


def resolve_path(payload: Any, path: str, depth: int = 0) -> Any:
    if depth > 8 or payload is None:
        return MISSING
    if path == "":
        return payload
    if isinstance(payload, dict):
        if path in payload:
            return payload[path]
        head, _, rest = path.partition(".")
        if head in payload:
            result = resolve_path(payload[head], rest, depth + 1)
            if result is not MISSING:
                return result
        for value in payload.values():
            result = resolve_path(value, path, depth + 1)
            if result is not MISSING:
                return result
        return MISSING
    if isinstance(payload, list):
        if path.isdigit() and int(path) < len(payload):
            return payload[int(path)]
        for item in payload:
            result = resolve_path(item, path, depth + 1)
            if result is not MISSING:
                return result
        return MISSING
    return MISSING


def type_matches(value: Any, expected: str) -> bool:
    if expected in {"any", "present", "xml"}:
        return value is not MISSING and value is not None
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


def normalize_unit(value: Any) -> str:
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
        "dollar": "usd",
        "dollars": "usd",
        "pkr": "pkr",
        "rupee": "pkr",
        "rupees": "pkr",
    }.get(text, text)


def units_match(actual: Any, expected: str) -> bool:
    return normalize_unit(actual) == normalize_unit(expected)


def _fail(
    outcome: ProbeOutcome,
    reason: str,
    actual: Any = None,
    checks: list[str] | None = None,
    field_path: str = "",
    expected: str = "",
) -> ClaimProbeCheck:
    return ClaimProbeCheck(
        outcome=outcome,
        reason=reason,
        field_path=field_path,
        actual_value=actual,
        expected=expected,
        checks=checks or [],
    )


def evaluate_claim(claim, probe: ProbeResult, definition) -> ClaimProbeCheck:
    if not claim.probeable or not definition.probeable:
        return _fail(ProbeOutcome.NOT_PROBEABLE, "Claim is not probeable by a live call.")
    if not probe.ok:
        return _fail(ProbeOutcome.PROBE_ERROR, probe.error or "Probe did not return a usable response.")
    checks: list[str] = []
    if claim.claim_type.value == "authentication":
        expects_key = bool(claim.metadata.get("expects_key", False))
        unauthorized = probe.status_code in {401, 403}
        if expects_key:
            if unauthorized:
                checks.append("probe returned 401/403, consistent with a required key")
                return ClaimProbeCheck(ProbeOutcome.AGREES, "Authentication requirement confirmed by probe.", checks=checks)
            return _fail(ProbeOutcome.DISAGREES, "The claim says a key is required, but the probe succeeded without one.", probe.status_code, checks)
        if unauthorized:
            return _fail(ProbeOutcome.DISAGREES, "The claim says no key is required, but the probe was rejected.", probe.status_code, checks)
        checks.append("probe succeeded without an API key")
        return ClaimProbeCheck(ProbeOutcome.AGREES, "No-key claim confirmed by probe.", checks=checks)
    if claim.claim_type.value == "limit":
        path = None
        if claim.expected_limit is not None:
            path = definition.limit_paths.get(str(claim.expected_limit))
        if not path and definition.limit_paths:
            path = next(iter(definition.limit_paths.values()))
        if not path:
            return _fail(ProbeOutcome.NOT_PROBEABLE, "No deterministic limit path is defined for this claim.")
        value = resolve_path(probe.payload, path)
        if value is MISSING:
            return _fail(ProbeOutcome.DISAGREES, f"Limit evidence field {path} is missing.", checks=checks, field_path=path)
        if isinstance(value, list):
            observed = len(value)
        elif isinstance(value, (int, float)):
            observed = value
        else:
            return _fail(ProbeOutcome.DISAGREES, f"Limit evidence field {path} has unusable type.", value, checks, field_path=path)
        if claim.expected_limit is not None and observed >= claim.expected_limit:
            checks.append(f"observed {observed} items at {path}")
            return ClaimProbeCheck(ProbeOutcome.AGREES, f"Limit claim confirmed: observed {observed} at {path}.", path, observed, str(claim.expected_limit), checks)
        if claim.expected_limit is not None and observed < claim.expected_limit:
            return _fail(ProbeOutcome.DISAGREES, f"Observed limit {observed} is below claimed {claim.expected_limit}.", observed, checks, field_path=path, expected=str(claim.expected_limit))
        checks.append(f"observed {observed} items at {path}")
        return ClaimProbeCheck(ProbeOutcome.AGREES, f"Observed limit evidence at {path}.", path, observed, str(claim.expected_limit), checks)
    field_path = claim.field_path or ""
    if field_path == "" and claim.expected_type in {"array", "object", "xml"}:
        if type_matches(probe.payload, claim.expected_type):
            checks.append(f"root payload matches {claim.expected_type}")
            return ClaimProbeCheck(ProbeOutcome.AGREES, f"Payload root is a {claim.expected_type}.", "", None, claim.expected_type, checks)
        return _fail(ProbeOutcome.DISAGREES, f"Payload root is not a {claim.expected_type}.", type(probe.payload).__name__, checks)
    if not field_path:
        return _fail(ProbeOutcome.NOT_PROBEABLE, "Claim has no probeable field path.")
    value = resolve_path(probe.payload, field_path)
    if value is MISSING:
        return _fail(ProbeOutcome.DISAGREES, f"Mapped field {field_path} is missing from the response.", field_path=field_path)
    checks.append(f"field {field_path} is present")
    if claim.expected_type and claim.expected_type != "present" and not type_matches(value, claim.expected_type):
        return _fail(ProbeOutcome.DISAGREES, f"Field {field_path} has the wrong type.", value, checks, field_path=field_path, expected=claim.expected_type or "")
    checks.append(f"field {field_path} has type {claim.expected_type or 'present'}")
    if claim.expected_min is not None or claim.expected_max is not None:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return _fail(ProbeOutcome.DISAGREES, f"Range check needs a number at {field_path}.", value, checks, field_path=field_path)
        if claim.expected_min is not None and value < claim.expected_min:
            return _fail(ProbeOutcome.DISAGREES, f"Value at {field_path} is below the plausible range.", value, checks, field_path=field_path, expected=str(claim.expected_min))
        if claim.expected_max is not None and value > claim.expected_max:
            return _fail(ProbeOutcome.DISAGREES, f"Value at {field_path} is above the plausible range.", value, checks, field_path=field_path, expected=str(claim.expected_max))
        checks.append(f"value at {field_path} is within the plausible range")
    unit_path = definition.unit_paths.get(field_path)
    if claim.expected_unit and unit_path:
        unit_value = resolve_path(probe.payload, unit_path)
        if unit_value is MISSING:
            return _fail(ProbeOutcome.DISAGREES, f"Unit field {unit_path} is missing.", checks=checks, field_path=unit_path)
        if not units_match(unit_value, claim.expected_unit):
            return _fail(ProbeOutcome.DISAGREES, f"Unit at {unit_path} is {unit_value}, not {claim.expected_unit}.", unit_value, checks, field_path=field_path, expected=str(claim.expected_unit))
        checks.append(f"unit at {unit_path} matches {claim.expected_unit}")
    return ClaimProbeCheck(ProbeOutcome.AGREES, f"Probe agrees with claim about {field_path}.", field_path, value, claim.expected_unit or claim.expected_type or "", checks)


def validate_payload(definition, payload: Any) -> PayloadValidation:
    issues: list[ValidationIssue] = []
    for path, spec in definition.expected_fields.items():
        value = resolve_path(payload, path)
        if value is MISSING:
            if spec.required:
                issues.append(ValidationIssue(path, "Required mapped field is missing.", spec.expected_type, "missing"))
            continue
        if not type_matches(value, spec.expected_type):
            issues.append(ValidationIssue(path, "Mapped field has the wrong type.", spec.expected_type, type(value).__name__))
            continue
        if spec.minimum is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value < spec.minimum:
            issues.append(ValidationIssue(path, "Value is below the mapped range.", str(spec.minimum), str(value)))
        if spec.maximum is not None and isinstance(value, (int, float)) and not isinstance(value, bool) and value > spec.maximum:
            issues.append(ValidationIssue(path, "Value is above the mapped range.", str(spec.maximum), str(value)))
        if spec.unit:
            unit_path = definition.unit_paths.get(path)
            if unit_path:
                unit_value = resolve_path(payload, unit_path)
                if unit_value is not MISSING and not units_match(unit_value, spec.unit):
                    issues.append(ValidationIssue(unit_path, "Mapped unit does not match.", spec.unit, str(unit_value)))
    return PayloadValidation(ok=not issues, issues=issues, checked_fields=len(definition.expected_fields))
