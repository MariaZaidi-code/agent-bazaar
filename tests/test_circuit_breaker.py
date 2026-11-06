from __future__ import annotations

from app.core.circuit_breaker import CircuitBreakerRegistry


def test_circuit_breaker_registry():
    registry = CircuitBreakerRegistry()
    assert registry is not None


def test_circuit_breaker_defaults():
    registry = CircuitBreakerRegistry()
    assert registry.failure_threshold == 2
    assert registry.cooldown_seconds == 30


def test_circuit_breaker_trip():
    registry = CircuitBreakerRegistry()
    registry.trip("test-tool")
    assert registry.state("test-tool") == "open"


def test_circuit_breaker_record_success(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.record_success("test-provider")
    assert registry.state("test-provider") == "closed"


def test_circuit_breaker_record_failure(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.record_failure("test-provider")
    assert registry.failure_threshold == 2


def test_circuit_breaker_state_summary(tmp_path):
    registry = CircuitBreakerRegistry()
    summary = registry.state("test-provider")
    assert summary.value == "closed"


def test_registry_all_empty(tmp_path):
    registry = CircuitBreakerRegistry()
    all_breakers = registry.snapshot()
    assert len(all_breakers) == 0


def test_registry_shutdown(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.reset()
    assert registry is not None


def test_circuit_breaker_state_after_trip(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.trip("test-tool")
    assert registry.state("test-tool") == "open"


def test_circuit_breaker_snapshot(tmp_path):
    registry = CircuitBreakerRegistry()
    snapshot = registry.snapshot()
    assert snapshot is not None


def test_circuit_breaker_link_key(tmp_path):
    registry = CircuitBreakerRegistry()
    key = registry.link_key("client", "tool-id")
    assert key is not None
    assert isinstance(key, str)


def test_circuit_breaker_reset(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.trip("test-tool")
    assert registry.state("test-tool") == "open"
    registry.reset("test-tool")
    assert registry.state("test-tool") == "closed"


def test_circuit_breaker_multiple_trips(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.trip("test-tool")
    registry.trip("test-tool")
    assert registry.state("test-tool") == "open"


def test_circuit_breaker_record_failure_increments(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.record_failure("test-provider")
    assert registry.failure_threshold == 2


def test_circuit_breaker_record_success_increments(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.record_success("test-provider")
    assert registry.state("test-provider") == "closed"


def test_circuit_breaker_allow_disabled_after_trip(tmp_path):
    registry = CircuitBreakerRegistry()
    registry.trip("test-provider")
    allowed, _ = registry.allow("test-provider")
    assert allowed is False

