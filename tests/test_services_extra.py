from __future__ import annotations

from app.services import build_services
from app.config import Settings


def test_build_services_creates_all_components(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services is not None
    assert services.graph is not None
    assert services.ontology is not None
    assert services.trust is not None
    assert services.providers is not None


def test_build_services_has_webhooks(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.webhooks is not None


def test_build_services_has_jobs(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.jobs is not None


def test_build_services_has_mcp_manager(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.mcp is not None


def test_build_services_has_auth(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.auth is not None


def test_build_services_has_scheduler(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.scheduler is not None


def test_build_services_has_scheduled_runs(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.scheduled_runs is not None


def test_build_services_shutdown(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    services.shutdown()


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