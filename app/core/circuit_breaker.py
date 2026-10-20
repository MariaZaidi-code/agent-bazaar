from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.schemas import BreakerStatus


@dataclass
class BreakerRecord:
    key: str
    state: BreakerStatus = BreakerStatus.closed
    consecutive_failures: int = 0
    opened_at: float | None = None
    trial_in_flight: bool = False
    last_error: str = ""
    transitions: list[dict[str, Any]] = field(default_factory=list)


class CircuitBreakerRegistry:
    def __init__(
        self,
        failure_threshold: int = 2,
        cooldown_seconds: int = 30,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_seconds = max(0, cooldown_seconds)
        self.clock = clock
        self._records: dict[str, BreakerRecord] = {}
        self._lock = threading.RLock()

    @staticmethod
    def link_key(client: str, provider_id: str) -> str:
        return f"{client}->{provider_id}"

    def _record(self, key: str) -> BreakerRecord:
        record = self._records.get(key)
        if record is None:
            record = BreakerRecord(key=key)
            self._records[key] = record
        return record

    def _transition(self, record: BreakerRecord, state: BreakerStatus, reason: str) -> None:
        if record.state != state:
            record.transitions.append(
                {
                    "at": self.clock(),
                    "from": record.state.value,
                    "to": state.value,
                    "reason": reason,
                }
            )
            if len(record.transitions) > 25:
                record.transitions = record.transitions[-25:]
        record.state = state

    def allow(self, key: str) -> tuple[bool, BreakerStatus]:
        with self._lock:
            record = self._record(key)
            if record.state == BreakerStatus.closed:
                return True, record.state
            if record.state == BreakerStatus.open:
                opened_at = record.opened_at or 0.0
                if self.clock() - opened_at >= self.cooldown_seconds:
                    self._transition(record, BreakerStatus.half_open, "cool-down elapsed")
                    record.trial_in_flight = True
                    return True, record.state
                return False, record.state
            if record.trial_in_flight:
                return False, record.state
            record.trial_in_flight = True
            return True, record.state

    def record_success(self, key: str, reason: str = "call succeeded") -> BreakerStatus:
        with self._lock:
            record = self._record(key)
            record.consecutive_failures = 0
            record.trial_in_flight = False
            record.opened_at = None
            self._transition(record, BreakerStatus.closed, reason)
            return record.state

    def record_failure(self, key: str, reason: str = "call failed") -> BreakerStatus:
        with self._lock:
            record = self._record(key)
            record.last_error = reason
            record.trial_in_flight = False
            if record.state == BreakerStatus.half_open:
                record.opened_at = self.clock()
                self._transition(record, BreakerStatus.open, reason)
                return record.state
            record.consecutive_failures += 1
            if record.consecutive_failures >= self.failure_threshold:
                record.opened_at = self.clock()
                self._transition(record, BreakerStatus.open, reason)
            return record.state

    def trip(self, key: str, reason: str = "drift alert") -> BreakerStatus:
        with self._lock:
            record = self._record(key)
            record.opened_at = self.clock()
            record.last_error = reason
            record.trial_in_flight = False
            self._transition(record, BreakerStatus.open, reason)
            return record.state

    def reset(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._records.clear()
                return
            record = self._records.get(key)
            if record is not None:
                record.state = BreakerStatus.closed
                record.consecutive_failures = 0
                record.opened_at = None
                record.trial_in_flight = False
                record.last_error = ""
                record.transitions.clear()

    def state(self, key: str) -> BreakerStatus:
        with self._lock:
            return self._record(key).state

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._records.values())
        return [
            {
                "key": record.key,
                "state": record.state.value,
                "consecutive_failures": record.consecutive_failures,
                "opened_at": record.opened_at,
                "last_error": record.last_error,
                "transitions": record.transitions[-5:],
            }
            for record in sorted(records, key=lambda item: item.key)
        ]
