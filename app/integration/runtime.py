"""Wiring between the knowledge layer and the app runtime.

The app can run on its own local fallback ontology and tool catalogue, or on the
knowledge layer's RDF graph and Mapper. :func:`build_knowledge_layer` returns
the knowledge-layer objects when the published artifacts are available, so the
app can use the canonical ontology, the RDF tool graph and the real Mapper.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from agent_bazaar.config import PathSettings, Settings as KnowledgeSettings, ensure_directories
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.vec import build_vector_service
from app.config import Settings
from app.integration.graph_adapter import RdfToolGraph
from app.integration.mapper_adapter import KnowledgeMapper
from app.integration.ontology_bridge import KnowledgeOntology


@dataclass
class KnowledgeLayer:
    store: KgStore
    ontology: KnowledgeOntology
    graph: RdfToolGraph
    mapper: KnowledgeMapper
    settings: KnowledgeSettings


def knowledge_artifacts_available(settings: Settings) -> bool:
    return Path(settings.knowledge_graph_file).exists()


def _knowledge_settings(settings: Settings) -> KnowledgeSettings:
    root = Path(settings.runtime_dir) / "knowledge"
    paths = PathSettings(
        data_dir=root,
        specs_dir=root / "specs",
        cache_dir=root / "cache",
        out_dir=root / "out",
        memory_dir=root / "memory",
        staging_dir=root / "staging",
        vectors_dir=root / "vectors",
    )
    knowledge = KnowledgeSettings(paths=paths)
    return ensure_directories(knowledge)


def build_knowledge_layer(
    settings: Settings,
    *,
    local_ontology: object,
    local_graph: object,
    local_mapper: object | None = None,
) -> KnowledgeLayer | None:
    """Build the knowledge-layer runtime, or None when the artifacts are missing."""
    if not knowledge_artifacts_available(settings):
        return None
    knowledge = _knowledge_settings(settings)
    store = KgStore.build_default(
        load_existing=True,
        ontology_path=settings.knowledge_ontology_file,
        graph_path=settings.knowledge_graph_file,
    )
    vector = build_vector_service(knowledge, force_fallback=True)
    mapper_agent = MapperAgent(
        store,
        vector,
        client=None,
        ingester=IngestionUtility(knowledge.ingestion),
        settings=knowledge,
        use_llm=False,
    )
    ontology = KnowledgeOntology(store, local=local_ontology)
    graph = RdfToolGraph(store, local_graph=local_graph, ontology=ontology)
    mapper = KnowledgeMapper(mapper_agent, store, local_stub=local_mapper)
    return KnowledgeLayer(
        store=store,
        ontology=ontology,
        graph=graph,
        mapper=mapper,
        settings=knowledge,
    )
