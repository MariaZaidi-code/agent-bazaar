"""Integration tests for the knowledge-layer Mapper behind the app's mapper API."""

from __future__ import annotations

from pathlib import Path

from agent_bazaar.config import PathSettings, Settings
from agent_bazaar.kg import KgStore
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.mapper.memory import CorrectionMemory
from agent_bazaar.mapper.staging import StagingQueue
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.ns import AB
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.vec import HashingEmbedder, VectorIndex, VectorService
from app.integration.mapper_adapter import KnowledgeMapper
from app.schemas import ConceptSpec, CorrectionRequest, ListingIngestRequest


def _settings(root: Path) -> Settings:
    return Settings(
        paths=PathSettings(
            data_dir=root,
            specs_dir=root / "specs",
            cache_dir=root / "cache",
            out_dir=root / "out",
            memory_dir=root / "memory",
            staging_dir=root / "staging",
            vectors_dir=root / "vectors",
        )
    )


def _store() -> KgStore:
    graph = upper_with_units()
    for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
        graph.add(triple)
    return KgStore(graph=graph)


def _adapter(root: Path) -> tuple[KnowledgeMapper, KgStore]:
    settings = _settings(root)
    store = _store()
    vector = VectorService(HashingEmbedder(dim=384), VectorIndex(384))
    agent = MapperAgent(
        store,
        vector,
        client=None,
        settings=settings,
        memory=CorrectionMemory(settings.paths.memory_dir),
        staging=StagingQueue(settings.paths.staging_dir),
        use_llm=False,
    )
    return KnowledgeMapper(agent, store), store


def _listing() -> ListingIngestRequest:
    return ListingIngestRequest(
        name="Demo Forecast Listing",
        description="Returns the air temperature of a place.",
        capability="GetWeatherForecast",
        inputs=[
            ConceptSpec(
                concept="PlaceName",
                name="place_name",
                datatype="string",
                description="Place to look up.",
            )
        ],
        outputs=[
            ConceptSpec(
                concept="Temperature",
                name="temperature_2m",
                unit="C",
                datatype="float",
                description="Air temperature at two metres.",
            )
        ],
    )


def _correction(tool_id: str) -> CorrectionRequest:
    return CorrectionRequest(
        tool_id=tool_id,
        field_name="temperature_2m",
        original_concept="Temperature",
        corrected_concept="FeelsLikeTemperature",
        corrected_unit="Celsius",
        note="The provider returns the apparent temperature.",
    )


def test_valid_listing_is_accepted_and_returns_typed_fields(tmp_path: Path) -> None:
    adapter, store = _adapter(tmp_path)

    result = adapter.submit_listing(_listing(), correlation_id="corr-listing")

    assert result.accepted is True
    assert result.violations == []
    assert result.tool_id.startswith("listing_")
    assert result.correlation_id == "corr-listing"
    assert [item.concept for item in result.inputs] == ["PlaceName"]
    assert [item.concept for item in result.outputs] == ["Temperature"]
    assert result.outputs[0].name == "temperature_2m"
    assert result.outputs[0].unit == "Celsius"
    assert result.outputs[0].datatype == "float"
    assert store.concept_for_field(result.tool_id, "output.temperature_2m") == str(AB.Temperature)
    assert store.concept_for_field(result.tool_id, "input.place_name") == str(AB.PlaceName)


def test_listing_with_unknown_concept_is_rejected(tmp_path: Path) -> None:
    adapter, store = _adapter(tmp_path)
    request = _listing()
    request.inputs = [
        ConceptSpec(concept="NoSuchConcept", name="zwibble_flux", datatype="string")
    ]

    result = adapter.submit_listing(request, correlation_id="corr-unknown")

    assert result.accepted is False
    assert result.violations
    assert any("NoSuchConcept" in violation for violation in result.violations)
    assert store.concept_for_field(result.tool_id, "output.temperature_2m") is None
    assert store.concept_for_field(result.tool_id, "input.zwibble_flux") is None


def test_valid_correction_is_promoted_and_changes_the_graph(tmp_path: Path) -> None:
    adapter, store = _adapter(tmp_path)
    listing = adapter.submit_listing(_listing(), correlation_id="corr-correction")
    assert listing.accepted is True
    assert store.concept_for_field(listing.tool_id, "output.temperature_2m") == str(AB.Temperature)

    result = adapter.submit_correction(_correction(listing.tool_id), correlation_id="corr-correction")

    assert result.accepted is True
    assert result.violations == []
    assert result.correction_id.startswith("corr_")
    assert store.concept_for_field(listing.tool_id, "output.temperature_2m") == str(
        AB.FeelsLikeTemperature
    )


def test_correction_with_unknown_concept_is_rejected(tmp_path: Path) -> None:
    adapter, store = _adapter(tmp_path)
    listing = adapter.submit_listing(_listing(), correlation_id="corr-bad-correction")
    request = _correction(listing.tool_id)
    request.corrected_concept = "NoSuchConcept"

    result = adapter.submit_correction(request, correlation_id="corr-bad-correction")

    assert result.accepted is False
    assert result.violations
    assert any("NoSuchConcept" in violation for violation in result.violations)
    assert store.concept_for_field(listing.tool_id, "output.temperature_2m") == str(AB.Temperature)


def test_listing_with_external_concept_is_accepted_but_not_promoted(tmp_path: Path) -> None:
    adapter, store = _adapter(tmp_path)
    request = ListingIngestRequest(
        name="Research Paper Listing",
        description="Searches research papers.",
        capability="SearchResearchPapers",
        outputs=[
            ConceptSpec(
                concept="ResearchPaper",
                name="paper",
                datatype="object",
                description="A research paper.",
            )
        ],
    )

    result = adapter.submit_listing(request, correlation_id="corr-external")

    assert result.accepted is True
    assert result.violations == []
    assert [item.concept for item in result.outputs] == ["ResearchPaper"]
    assert store.list_tools() == []
    assert adapter.staged()["listings"][0]["status"] == "staged"


def test_reset_clears_staged_items(tmp_path: Path) -> None:
    adapter, store = _adapter(tmp_path)
    listing = adapter.submit_listing(_listing(), correlation_id="corr-reset")
    adapter.submit_correction(_correction(listing.tool_id), correlation_id="corr-reset")

    staged = adapter.staged()
    assert len(staged["listings"]) == 1
    assert len(staged["corrections"]) == 1

    adapter.reset()

    assert adapter.staged() == {"corrections": [], "listings": []}
    assert store.concept_for_field(listing.tool_id, "output.temperature_2m") == str(
        AB.FeelsLikeTemperature
    )
