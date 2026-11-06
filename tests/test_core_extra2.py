from __future__ import annotations

from app.core.cache import Cache
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.observability import RequestMetrics
from app.core.jobs import JobManager
from app.core.webhooks import WebhookRegistry


def test_request_metrics_record():
    metrics = RequestMetrics()
    metrics.record("GET", "/api/tools", 200, 10.5)
    metrics.record("GET", "/api/tools", 200, 15.5)
    metrics.record("POST", "/api/tasks", 500, 50.0)

    snapshot = metrics.snapshot()
    assert snapshot["requests"] == 3
    assert snapshot["statuses"]["200"] == 2
    assert snapshot["statuses"]["500"] == 1
    assert snapshot["endpoints"]["GET /api/tools"]["count"] == 2


def test_circuit_breaker_request_flow():
    registry = CircuitBreakerRegistry()
    # All requests should be allowed when breaker is closed
    for _ in range(10):
        allowed, _ = registry.allow("test-provider")
        assert allowed is True


def test_circuit_breaker_opens_after_failures():
    registry = CircuitBreakerRegistry(failure_threshold=3)
    for _ in range(3):
        registry.record_failure("test-provider")
    assert registry.state("test-provider").value == "open"


def test_circuit_breaker_reset_after_trip(tmp_path):
    registry = CircuitBreakerRegistry(failure_threshold=1)
    registry.trip("test-provider")
    assert registry.state("test-provider") == "open"
    registry.reset("test-provider")
    assert registry.state("test-provider") == "closed"


def test_trust_registry_record_probe(tmp_path):
    from app.core.trust_registry import TrustRegistry
    trust = TrustRegistry(tmp_path / "trust.db")
    trust.record_probe("test-tool", True, "probe test")
    rows = trust.all()
    assert len(rows) >= 0


def test_trust_registry_get_trust(tmp_path):
    from app.core.trust_registry import TrustRegistry
    trust = TrustRegistry(tmp_path / "trust.db")
    trust.record_probe("test-tool", True, "probe test")
    score = trust.get("test-tool")
    assert score is not None


def test_version_manifest(tmp_path):
    from app.core.versioning import build_version_manifest
    from app.config import Settings
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    manifest = build_version_manifest(settings, {}, {})
    assert manifest is not None
    assert "concepts" in manifest["counts"]
    assert "tools" in manifest["counts"]
    assert "artifacts" in manifest