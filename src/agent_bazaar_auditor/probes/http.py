from __future__ import annotations

import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


class TransportError(RuntimeError):
    pass


@dataclass
class HttpResponse:
    status_code: int
    body: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    elapsed_ms: float = 0.0


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep) -> None:
        self.clock = clock
        self.sleep = sleep
        self.last_call: dict[str, float] = {}

    def wait(self, key: str, minimum_interval: float) -> float:
        now = self.clock()
        previous = self.last_call.get(key)
        delay = 0.0
        if previous is not None:
            elapsed = now - previous
            if elapsed < minimum_interval:
                delay = minimum_interval - elapsed
                if delay > 0:
                    self.sleep(delay)
        self.last_call[key] = self.clock()
        return delay


class HttpTransport:
    RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})

    def __init__(
        self,
        timeout: float = 15.0,
        retries: int = 2,
        backoff_seconds: float = 0.25,
        max_backoff_seconds: float = 2.0,
        retry_statuses: frozenset[int] | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = timeout
        self.retries = max(0, retries)
        self.backoff_seconds = max(0.0, backoff_seconds)
        self.max_backoff_seconds = max(0.0, max_backoff_seconds)
        self.retry_statuses = retry_statuses or self.RETRY_STATUSES
        self.sleep = sleep

    def _delay(self, attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), self.max_backoff_seconds))
            except ValueError:
                pass
        return min(self.backoff_seconds * (2**attempt), self.max_backoff_seconds)

    def get(self, url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> HttpResponse:
        query = urllib.parse.urlencode(params or {}, doseq=True)
        full_url = f"{url}?{query}" if query else url
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            request = urllib.request.Request(full_url, headers=headers or {}, method="GET")
            started = time.monotonic()
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    body = response.read().decode("utf-8", errors="replace")
                    elapsed = (time.monotonic() - started) * 1000.0
                    return HttpResponse(
                        status_code=response.status,
                        body=body,
                        url=response.geturl(),
                        headers={key: value for key, value in response.headers.items()},
                        elapsed_ms=elapsed,
                    )
            except urllib.error.HTTPError as error:
                last_error = error
                if attempt < self.retries and error.code in self.retry_statuses:
                    retry_after = error.headers.get("Retry-After") if error.headers else None
                    self.sleep(self._delay(attempt, retry_after))
                    continue
                body = error.read().decode("utf-8", errors="replace")
                elapsed = (time.monotonic() - started) * 1000.0
                return HttpResponse(
                    status_code=error.code,
                    body=body,
                    url=error.geturl(),
                    headers={key: value for key, value in error.headers.items()},
                    elapsed_ms=elapsed,
                )
            except (urllib.error.URLError, TimeoutError, OSError) as error:
                last_error = error
                if attempt < self.retries:
                    self.sleep(self._delay(attempt))
                    continue
                raise TransportError(str(error)) from error
        raise TransportError(str(last_error) if last_error else "transport failed without an error")
