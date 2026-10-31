from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any


class RequestMetrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: dict[str, int] = defaultdict(int)
        self._statuses: dict[int, int] = defaultdict(int)
        self._durations_ms: dict[str, float] = defaultdict(float)
        self._errors = 0

    def record(self, method: str, path: str, status: int, duration_ms: float) -> None:
        key = f"{method.upper()} {path}"
        with self._lock:
            self._requests[key] += 1
            self._statuses[status] += 1
            self._durations_ms[key] += max(0.0, duration_ms)
            if status >= 500:
                self._errors += 1

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = sum(self._requests.values())
            durations = dict(self._durations_ms)
            requests = dict(self._requests)
            statuses = {str(status): count for status, count in sorted(self._statuses.items())}
            errors = self._errors
        endpoints = {
            key: {
                "count": requests[key],
                "average_ms": round(durations.get(key, 0.0) / requests[key], 3),
            }
            for key in sorted(requests)
        }
        return {
            "requests": total,
            "errors": errors,
            "statuses": statuses,
            "endpoints": endpoints,
        }


class SlidingWindowRateLimiter:
    def __init__(
        self,
        limit: int = 120,
        window_seconds: float = 60.0,
        clock=time.monotonic,
    ) -> None:
        self.limit = max(0, limit)
        self.window_seconds = max(0.0, window_seconds)
        self.clock = clock
        self._lock = threading.Lock()
        self._calls: dict[str, deque[float]] = defaultdict(deque)

    def allow(self, key: str) -> tuple[bool, float]:
        if self.limit == 0:
            return True, 0.0
        now = self.clock()
        cutoff = now - self.window_seconds
        with self._lock:
            calls = self._calls[key]
            while calls and calls[0] <= cutoff:
                calls.popleft()
            if len(calls) >= self.limit:
                retry_after = max(0.0, calls[0] + self.window_seconds - now)
                return False, retry_after
            calls.append(now)
        return True, 0.0
