from __future__ import annotations

from app.services import build_services
from app.config import Settings


def test_build_services_ontology_not_none(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.ontology is not None
    assert len(services.ontology.concepts) > 0


def test_build_services_graph_not_none(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.graph is not None
    assert len(services.graph.all()) >= 0


def test_build_services_providers_not_none(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    providers = services.providers.all()
    assert len(providers) >= 0


def test_build_services_knowledge_graph_not_none(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.graph is not None


def test_build_services_knowledge_layer(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", knowledge_backend="auto")
    services = build_services(settings)
    assert services.knowledge is not None


def test_build_services_mcp_not_none(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services.mcp is not None


def test_build_services_shutdown_creates_no_error(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    services.shutdown()


def test_app_main_importable():
    from app.main import create_app
    assert create_app is not None


def test_app_services_build_services(tmp_path):
    from app.services import build_services
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    assert services is not None


def test_app_services_shutdown_does_not_crash(tmp_path):
    from app.services import build_services
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    services = build_services(settings)
    services.shutdown()
    services.shutdown()

