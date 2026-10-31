from __future__ import annotations

import copy
import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..enums import MockBehavior, ProbeSource
from ..probes.definitions import ProbeDefinition
from ..utils import append_jsonl, utc_now

UNIT_SYMBOLS = {
    "celsius": "°C",
    "fahrenheit": "°F",
    "kelvin": "K",
    "km": "km",
    "m": "m",
    "usd": "USD",
    "pkr": "PKR",
}


@dataclass
class ProviderResponse:
    status_code: int
    payload: Any
    raw_text: str = ""
    error: str = ""
    latency_ms: float = 0.0
    timestamp: str = field(default_factory=utc_now)
    url: str = ""
    source: ProbeSource = ProbeSource.MOCK
    metadata: dict[str, Any] = field(default_factory=dict)


class Provider(Protocol):
    tool_id: str

    def call(self, request: dict[str, Any]) -> ProviderResponse:
        ...

    def configure(self, behavior: str, **options: Any) -> None:
        ...

    def state(self) -> dict[str, Any]:
        ...


def _walk_path(node: Any, parts: list[str], action: Any) -> None:
    if not parts:
        return
    if isinstance(node, list):
        for item in node:
            _walk_path(item, parts, action)
        return
    if not isinstance(node, dict):
        return
    head = parts[0]
    if len(parts) == 1:
        if head in node:
            action(node, head)
            return
    elif head in node:
        child = node[head]
        if isinstance(child, dict):
            _walk_path(child, parts[1:], action)
        elif isinstance(child, list):
            for item in child:
                _walk_path(item, parts[1:], action)
        return
    for value in node.values():
        if isinstance(value, (dict, list)):
            _walk_path(value, parts, action)


def rename_path(payload: Any, field_path: str, new_name: str) -> Any:
    parts = field_path.split(".") if field_path else []
    if not parts:
        return payload

    def action(node: dict[str, Any], key: str) -> None:
        node[new_name] = node.pop(key)

    _walk_path(payload, parts, action)
    return payload


def remove_path(payload: Any, field_path: str) -> Any:
    parts = field_path.split(".") if field_path else []
    if not parts:
        return payload

    def action(node: dict[str, Any], key: str) -> None:
        node.pop(key, None)

    _walk_path(payload, parts, action)
    return payload


def set_path_value(payload: Any, field_path: str, value: Any) -> int:
    parts = field_path.split(".") if field_path else []
    if not parts:
        return 0
    replaced = 0

    def action(node: dict[str, Any], key: str) -> None:
        nonlocal replaced
        node[key] = copy.deepcopy(value)
        replaced += 1

    _walk_path(payload, parts, action)
    return replaced


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    source = from_unit.lower()
    target = to_unit.lower()
    if source == target:
        return value
    if source == "celsius" and target == "fahrenheit":
        return value * 9.0 / 5.0 + 32.0
    if source == "fahrenheit" and target == "celsius":
        return (value - 32.0) * 5.0 / 9.0
    if source == "celsius" and target == "kelvin":
        return value + 273.15
    if source == "kelvin" and target == "celsius":
        return value - 273.15
    if source == "km" and target == "m":
        return value * 1000.0
    if source == "m" and target == "km":
        return value / 1000.0
    return value


class MockProvider:
    def __init__(
        self,
        tool_id: str,
        definition: ProbeDefinition,
        behavior: MockBehavior | str = MockBehavior.NORMAL,
        options: dict[str, Any] | None = None,
        seed: int = 7,
        log_path: Path | str | None = None,
        documentation: list[str] | None = None,
    ) -> None:
        self.tool_id = tool_id
        self.definition = definition
        self.seed = seed
        self.behavior = MockBehavior(behavior)
        self.options = dict(options or {})
        self.log_path = Path(log_path) if log_path else None
        self.documentation = list(documentation or [])
        self.call_count = 0
        self.behavior_calls = 0
        self.events: list[dict[str, Any]] = []
        self._log_event("initialized", self.behavior, self.options)

    def _log_event(self, event: str, behavior: MockBehavior, options: dict[str, Any] | None = None) -> None:
        record = {
            "event": event,
            "tool_id": self.tool_id,
            "behavior": behavior.value,
            "options": dict(options or {}),
            "timestamp": utc_now(),
            "seed": self.seed,
            "call_count": self.call_count,
        }
        self.events.append(record)
        if self.log_path is not None:
            append_jsonl(self.log_path, record)

    def configure(self, behavior: MockBehavior | str, **options: Any) -> None:
        self.behavior = MockBehavior(behavior)
        self.options = dict(options)
        self.behavior_calls = 0
        self._log_event("configured", self.behavior, self.options)

    def reset(self) -> None:
        self.configure(MockBehavior.NORMAL)

    def state(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "behavior": self.behavior.value,
            "options": dict(self.options),
            "seed": self.seed,
            "call_count": self.call_count,
            "behavior_calls": self.behavior_calls,
            "events": list(self.events),
        }

    def _first_field(self) -> str:
        return next(iter(self.definition.expected_fields), "")

    def _default_unit_change(self) -> tuple[str, str, str, str]:
        if self.definition.unit_paths:
            field_path, unit_path = next(iter(self.definition.unit_paths.items()))
            field_spec = self.definition.expected_fields.get(field_path)
            from_unit = (field_spec.unit if field_spec else None) or "celsius"
        else:
            field_path = self._first_field()
            unit_path = ""
            field_spec = self.definition.expected_fields.get(field_path)
            from_unit = (field_spec.unit if field_spec else None) or "celsius"
        to_unit = "fahrenheit" if from_unit == "celsius" else "celsius"
        return field_path, unit_path, from_unit, to_unit

    def _apply_unit_change(self, payload: Any) -> None:
        field_path, unit_path, from_unit, to_unit = self._default_unit_change()
        field_path = self.options.get("field_path", field_path)
        unit_path = self.options.get("unit_path", unit_path)
        from_unit = self.options.get("from_unit", from_unit)
        to_unit = self.options.get("to_unit", to_unit)
        value = _read_path(payload, field_path)
        if isinstance(value, list):
            converted = [convert_unit(item, from_unit, to_unit) if isinstance(item, (int, float)) else item for item in value]
            set_path_value(payload, field_path, converted)
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            set_path_value(payload, field_path, convert_unit(float(value), from_unit, to_unit))
        if unit_path:
            symbol = self.options.get("unit_symbol", UNIT_SYMBOLS.get(to_unit, to_unit))
            set_path_value(payload, unit_path, symbol)

    def _apply_garbage(self, payload: Any, generator: random.Random) -> None:
        noise_keys = [
            "_debug",
            "garbage_blob",
            "noise",
            "unexpected_payload",
            "trace_dump",
            "unknown_section",
        ]
        targets: list[dict[str, Any]] = []
        if isinstance(payload, dict):
            targets.append(payload)
        elif isinstance(payload, list):
            targets.extend(item for item in payload if isinstance(item, dict))
        for target in targets:
            for index, key in enumerate(noise_keys):
                target[key] = {
                    "index": index,
                    "text": "".join(generator.choice("abcdef0123456789") for _ in range(18)),
                    "values": [generator.random() for _ in range(3)],
                }
            target.setdefault("meta", {})["served_by"] = "unverified-mock"

    def _simulate_failure(self, reason: str, latency: float) -> ProviderResponse:
        return ProviderResponse(
            status_code=503,
            payload=None,
            raw_text="",
            error=reason,
            latency_ms=latency,
            url=self.definition.endpoint,
            metadata={"mock_behavior": self.behavior.value, "injected": True},
        )

    def call(self, request: dict[str, Any]) -> ProviderResponse:
        self.call_count += 1
        self.behavior_calls += 1
        generator = random.Random(self.seed + self.call_count)
        latency = round(generator.uniform(20.0, 80.0), 2)
        effective = self.behavior

        if effective is MockBehavior.FLAPPING:
            fail_on = self.options.get("fail_on_calls") or [2, 4, 6, 8, 10]
            if self.behavior_calls in set(fail_on):
                response = self._simulate_failure("Simulated flapping failure.", round(generator.uniform(900.0, 1400.0), 2))
                self._log_event("call", self.behavior, {"failed": True})
                return response
            effective = MockBehavior.NORMAL

        if effective is MockBehavior.SLOW:
            latency = round(generator.uniform(2000.0, 4000.0), 2)

        if effective is MockBehavior.MALFORMED:
            response = ProviderResponse(
                status_code=200,
                payload=None,
                raw_text="{not-json",
                latency_ms=latency,
                url=self.definition.endpoint,
                metadata={"mock_behavior": self.behavior.value, "injected": True},
            )
            self._log_event("call", self.behavior, {"failed": False, "effective": effective.value})
            return response

        if effective is MockBehavior.OUTAGE:
            response = self._simulate_failure("Simulated outage (HTTP 503).", round(generator.uniform(1800.0, 3000.0), 2))
            self._log_event("call", self.behavior, {"failed": True})
            return response

        payload = copy.deepcopy(self.definition.fixture)

        if effective is MockBehavior.PARTIAL:
            field_path = self.options.get("field_path") or self._first_field()
            remove_path(payload, field_path)
        elif effective is MockBehavior.RENAME_FIELD:
            field_path = self.options.get("field_path") or self._first_field()
            new_name = self.options.get("new_name") or f"{field_path.split('.')[-1]}_renamed"
            rename_path(payload, field_path, new_name)
        elif effective is MockBehavior.REMOVE_FIELD:
            field_path = self.options.get("field_path") or self._first_field()
            remove_path(payload, field_path)
        elif effective is MockBehavior.UNIT_CHANGE:
            self._apply_unit_change(payload)
        elif effective is MockBehavior.TYPE_CHANGE:
            field_path = self.options.get("field_path") or self._first_field()
            replacement = self.options.get("replacement", "not-a-number")
            set_path_value(payload, field_path, replacement)
        elif effective is MockBehavior.GARBAGE_200:
            self._apply_garbage(payload, generator)
        elif effective is MockBehavior.DISHONEST:
            field_path = self.options.get("field_path")
            if field_path:
                self.options = {**self.options, "field_path": field_path}
            self._apply_unit_change(payload)
        elif effective is MockBehavior.EXAGGERATED_CLAIM:
            payload = copy.deepcopy(self.definition.fixture)

        raw_text = json.dumps(payload, ensure_ascii=False)
        self._log_event("call", self.behavior, {"failed": False, "effective": effective.value})
        return ProviderResponse(
            status_code=200,
            payload=payload,
            raw_text=raw_text,
            latency_ms=latency,
            url=self.definition.endpoint,
            metadata={
                "mock_behavior": self.behavior.value,
                "injected": self.behavior is not MockBehavior.NORMAL,
                "ground_truth": self.behavior.value,
            },
        )


def _read_path(payload: Any, path: str) -> Any:
    parts = path.split(".") if path else []
    current = payload
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list):
            values = []
            for item in current:
                if isinstance(item, dict) and part in item:
                    values.append(item[part])
            return values
        else:
            return None
    return current
