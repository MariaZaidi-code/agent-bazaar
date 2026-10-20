from __future__ import annotations

from app.services import AppServices


def test_ontology_links_and_units(services: AppServices) -> None:
    ontology = services.ontology
    assert ontology.exists("Temperature")
    assert ontology.is_subtype("Temperature", "Entity")
    assert ontology.is_subtype("CountryName", "LocationName")
    assert ontology.check_link("Coordinates", "degrees", "Coordinates", "degrees").valid
    compatible, conversion = ontology.units_compatible("C", "F")
    assert compatible is True
    assert conversion is True
    assert ontology.check_link("Country", None, "CountryName", None).valid is False
    assert ontology.check_link("Temperature", "C", "Coordinates", "degrees").valid is False


def test_all_seeded_tools_validate(services: AppServices) -> None:
    violations = {
        tool.id: issue
        for tool in services.graph.all()
        for issue in services.ontology.validate_tool(tool)
    }
    assert violations == {}
    assert all(not issues for issues in services.providers.validation.values())


def test_substitutes_share_capability(services: AppServices) -> None:
    substitutes = services.graph.compatible_substitutes(
        "GetWeatherForecast",
        ["Coordinates"],
        ["Temperature"],
    )
    ids = {tool.id for tool in substitutes}
    assert "open-meteo-forecast" in ids
    assert "open-meteo-forecast-backup" in ids
    assert "frankfurter-currency" not in ids


def test_metadata_concepts_are_not_capabilities(services: AppServices) -> None:
    for tool in services.graph.all():
        assert tool.capability in services.ontology.capabilities
        assert tool.capability not in {"Capability", "Claim", "Provider", "Service"}


def test_rdf_export_exists(services: AppServices) -> None:
    path = services.settings.runtime_dir / "knowledge_graph.ttl"
    assert path.exists()
    text = path.read_text(encoding="utf-8")
    assert "GetWeatherForecast" in text
    assert "Temperature" in text
