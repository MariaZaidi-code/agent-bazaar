from __future__ import annotations

from app.core.circuit_breaker import CircuitBreakerRegistry
from app.schemas import BreakerStatus


class FakeClock:
    def __init__(self) -> None:
        self.now = 100.0

    def __call__(self) -> float:
        return self.now


def test_opens_after_threshold() -> None:
    clock = FakeClock()
    breakers = CircuitBreakerRegistry(failure_threshold=2, cooldown_seconds=10, clock=clock)
    key = breakers.link_key("client", "provider")
    assert breakers.allow(key) == (True, BreakerStatus.closed)
    breakers.record_failure(key, "first")
    assert breakers.state(key) == BreakerStatus.closed
    breakers.record_failure(key, "second")
    assert breakers.state(key) == BreakerStatus.open
    assert breakers.allow(key) == (False, BreakerStatus.open)


def test_half_open_allows_one_trial_and_closes_on_success() -> None:
    clock = FakeClock()
    breakers = CircuitBreakerRegistry(failure_threshold=1, cooldown_seconds=5, clock=clock)
    key = breakers.link_key("client", "provider")
    breakers.record_failure(key, "outage")
    assert breakers.state(key) == BreakerStatus.open
    clock.now += 6
    allowed, state = breakers.allow(key)
    assert allowed is True
    assert state == BreakerStatus.half_open
    assert breakers.allow(key)[0] is False
    breakers.record_success(key)
    assert breakers.state(key) == BreakerStatus.closed


def test_half_open_reopens_on_failure() -> None:
    clock = FakeClock()
    breakers = CircuitBreakerRegistry(failure_threshold=1, cooldown_seconds=5, clock=clock)
    key = breakers.link_key("client", "provider")
    breakers.record_failure(key, "outage")
    clock.now += 6
    breakers.allow(key)
    breakers.record_failure(key, "trial failed")
    assert breakers.state(key) == BreakerStatus.open
    assert breakers.allow(key)[0] is False


def test_trip_and_snapshot() -> None:
    breakers = CircuitBreakerRegistry()
    key = breakers.link_key("client", "drifted")
    breakers.trip(key, "drift alert")
    snapshot = breakers.snapshot()
    assert snapshot[0]["key"] == key
    assert snapshot[0]["state"] == "open"
    assert snapshot[0]["last_error"] == "drift alert"
    breakers.reset()
    assert breakers.snapshot() == []
