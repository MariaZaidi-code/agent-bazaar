"""Tests for the merged knowledge layer and application wiring."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.integration.canonical import (
    canonical_capability,
    canonical_concept,
    canonical_unit,
    capability_for_concepts,
    units_compatible,
)
from app.main import create_app
from app.services import build_services

REPO_ROOT = Path(__file__).resolve().parent.parent


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        runtime_dir=tmp_path / "runtime",
        offline_mode=True,
        knowledge_graph_file=REPO_ROOT / "data" / "out" / "graph.ttl",
        knowledge_ontology_file=REPO_ROOT / "data" / "out" / "ontology.ttl",
    )


def test_canonical_vocabulary_maps_both_sides() -> None:
    assert canonical_concept("Coordinates") == "Position"
    assert canonical_concept("ab:Temperature") == "Temperature"
    assert canonical_concept("https://agent-bazaar.local/ontology#PlaceName") == "PlaceName"
    assert canonical_unit("C") == "Celsius"
    assert canonical_unit("degrees") == "Degree"
    assert canonical_unit(None) is None
    assert canonical_capability("weather-api") == "GetWeatherForecast"
    assert capability_for_concepts(["Temperature"]) == "GetWeatherForecast"
    assert units_compatible("C", "F") is True
    assert units_compatible("Celsius", "Percent") is False


def test_default_backend_uses_the_knowledge_mapper_and_the_local_catalogue(tmp_path) -> None:
    services = build_services(_settings(tmp_path))

    assert services.knowledge is not None
    assert type(services.mapper).__name__ == "KnowledgeMapper"
    assert type(services.ontology).__name__ == "Ontology"
    assert type(services.graph).__name__ == "ToolKnowledgeGraph"


def test_rdf_backend_serves_the_knowledge_layer(tmp_path) -> None:
    settings = _settings(tmp_path).model_copy(update={"knowledge_backend": "rdf"})

    services = build_services(settings)

    assert type(services.ontology).__name__ == "KnowledgeOntology"
    assert type(services.graph).__name__ == "RdfToolGraph"
    assert services.ontology.exists("Temperature")
    assert services.ontology.check_capability("weather-api", "GetWeatherForecast")
    assert any(tool.id == "citycontext-com" for tool in services.graph.all())
    assert any(tool.id == "open-meteo-forecast" for tool in services.graph.all())


def test_local_backend_ignores_the_knowledge_layer(tmp_path) -> None:
    settings = _settings(tmp_path).model_copy(update={"knowledge_backend": "local"})

    services = build_services(settings)

    assert services.knowledge is None
    assert type(services.mapper).__name__ == "MapperStub"


def test_knowledge_route_reports_the_rdf_layer(tmp_path) -> None:
    settings = _settings(tmp_path)
    app = create_app(settings)

    with TestClient(app) as client:
        response = client.get("/api/knowledge")

    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["concepts"] >= 60
    assert payload["graph"]["tools"] >= 8
