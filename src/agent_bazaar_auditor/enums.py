from __future__ import annotations

from enum import StrEnum


class ClaimLabel(StrEnum):
    VERIFIED = "Verified"
    SUPPORTED = "Supported"
    CONTRADICTED = "Contradicted"
    UNSUPPORTED = "Unsupported"


class ClaimType(StrEnum):
    OUTPUT_FIELD = "output_field"
    UNIT = "unit"
    AUTHENTICATION = "authentication"
    LIMIT = "limit"
    AVAILABILITY = "availability"
    BEHAVIOUR = "behaviour"


class DocStance(StrEnum):
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SILENT = "silent"


class ProbeOutcome(StrEnum):
    AGREES = "agrees"
    DISAGREES = "disagrees"
    NOT_PROBEABLE = "not_probeable"
    NOT_PROBED = "not_probed"
    PROBE_ERROR = "probe_error"


class DriftDetectorKind(StrEnum):
    RULE = "rule"
    EMBEDDING = "embedding"


class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class MockBehavior(StrEnum):
    NORMAL = "normal"
    SLOW = "slow"
    PARTIAL = "partial"
    MALFORMED = "malformed"
    RENAME_FIELD = "rename_field"
    UNIT_CHANGE = "unit_change"
    TYPE_CHANGE = "type_change"
    REMOVE_FIELD = "remove_field"
    GARBAGE_200 = "garbage_200"
    EXAGGERATED_CLAIM = "exaggerated_claim"
    OUTAGE = "outage"
    FLAPPING = "flapping"
    DISHONEST = "dishonest"


class TrustOutcome(StrEnum):
    PROBE_PASS = "probe_pass"
    PROBE_FAIL = "probe_fail"
    SCHEMA_VALID = "schema_valid"
    SCHEMA_INVALID = "schema_invalid"
    CALL_SUCCESS = "call_success"
    CALL_FAILURE = "call_failure"
    CONTRADICTION = "contradiction"
    DRIFT = "drift"
    RATING = "rating"


class ProbeSource(StrEnum):
    LIVE = "live"
    CACHE = "cache"
    FIXTURE = "fixture"
    MOCK = "mock"
    MANUAL = "manual"
