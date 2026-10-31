from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.auditor_bridge import AuditorBridge
from app.agents.client import ClientAgent
from app.agents.mapper_stub import MapperStub
from app.agents.planner import TaskPlanner
from app.baselines.b1 import B1ToolCalling
from app.baselines.b2 import B2RagOnly
from app.config import Settings
from app.core.cache import Cache
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.llm import LLMClient
from app.core.message_bus import MessageBus
from app.core.tracing import TraceStore
from app.core.trust_registry import TrustRegistry
from app.integration.graph_adapter import RdfToolGraph
from app.integration.mapper_adapter import KnowledgeMapper
from app.integration.ontology_bridge import KnowledgeOntology
from app.integration.runtime import KnowledgeLayer, build_knowledge_layer
from app.knowledge.graph import ToolKnowledgeGraph
from app.knowledge.ontology import Ontology
from app.knowledge.retrieval import GraphRAGRetriever
from app.platform import PlatformStore
from app.providers.registry import ProviderRegistry


@dataclass
class AppServices:
    settings: Settings
    cache: Cache
    traces: TraceStore
    trust: TrustRegistry
    breakers: CircuitBreakerRegistry
    ontology: Ontology | KnowledgeOntology
    graph: ToolKnowledgeGraph | RdfToolGraph
    retriever: GraphRAGRetriever
    llm: LLMClient
    providers: ProviderRegistry
    auditor: AuditorBridge
    mapper: MapperStub | KnowledgeMapper
    planner: TaskPlanner
    bus: MessageBus
    client: ClientAgent
    b1: B1ToolCalling
    b2: B2RagOnly
    platform: PlatformStore
    knowledge: KnowledgeLayer | None = None

    def export_graph(self) -> bool:
        trust = {item["provider_id"]: item for item in self.trust.all()}
        return self.graph.export_turtle(
            self.settings.runtime_dir / "knowledge_graph.ttl", trust=trust
        )

    def monitoring(self) -> dict[str, Any]:
        trust_rows = {item["provider_id"]: item for item in self.trust.all()}
        providers = []
        for provider in self.providers.all():
            trust = trust_rows.get(provider.provider_id, {})
            providers.append(
                {
                    "provider_id": provider.provider_id,
                    "tool_id": provider.tool_id,
                    "tool_name": provider.spec.name,
                    "capability": provider.spec.capability,
                    "execution": provider.spec.execution,
                    "trust": trust.get("score", 0.5),
                    "demoted": trust.get("demoted", False),
                    "contradictions": trust.get("contradictions", 0),
                    "calls": trust.get("calls", 0),
                    "probes": trust.get("probes", 0),
                    "failure_mode": (
                        "offline"
                        if (self.settings.offline_mode or provider.offline_forced)
                        else "live"
                    ),
                    "fail_next": provider.fail_next,
                }
            )
        return {
            "trust": self.trust.all(),
            "breakers": self.breakers.snapshot(),
            "drift_alerts": self.auditor.snapshot(),
            "auditor": self.auditor.status(),
            "providers": providers,
            "mode": "offline" if self.settings.offline_mode else "live",
        }

    def reset_demo(self) -> None:
        self.trust.reset()
        self.breakers.reset()
        self.auditor.reset()
        self.mapper.reset()
        self.providers.reset_demo()
        self.cache.clear()


def build_services(settings: Settings | None = None) -> AppServices:
    resolved = settings or Settings()
    resolved.ensure_dirs()
    local_ontology = Ontology.load(resolved.ontology_file)
    local_graph = ToolKnowledgeGraph(local_ontology)
    local_mapper = MapperStub(local_graph, local_ontology)
    knowledge = None
    if resolved.knowledge_backend in ("auto", "rdf"):
        knowledge = build_knowledge_layer(
            resolved,
            local_ontology=local_ontology,
            local_graph=local_graph,
            local_mapper=local_mapper,
        )
    if knowledge is not None and resolved.knowledge_backend == "rdf":
        ontology = knowledge.ontology
        graph = knowledge.graph
        mapper = knowledge.mapper
    else:
        ontology = local_ontology
        graph = local_graph
        mapper = knowledge.mapper if knowledge is not None else local_mapper
    cache = Cache(resolved.cache_db, ttl_seconds=resolved.cache_ttl_seconds)
    traces = TraceStore(resolved.traces_db)
    platform = PlatformStore(resolved.platform_db)
    trust = TrustRegistry(
        resolved.trust_db,
        signal_weights=resolved.trust_signal_weights,
        demotion_threshold=resolved.trust_demotion_threshold,
        min_evidence=resolved.trust_min_evidence,
    )
    breakers = CircuitBreakerRegistry(
        failure_threshold=resolved.breaker_failure_threshold,
        cooldown_seconds=resolved.breaker_cooldown_seconds,
    )
    llm = LLMClient(resolved, cache)
    providers = ProviderRegistry(resolved, cache, graph)
    retriever = GraphRAGRetriever(
        graph,
        top_k=resolved.ranking_top_k,
        expansion=resolved.graph_expansion,
    )
    auditor = AuditorBridge(
        graph,
        trust,
        resolved.auditor_dir,
        live=resolved.auditor_live,
        persist=resolved.auditor_persist,
    )
    planner = TaskPlanner(ontology, llm)
    bus = MessageBus(traces)
    client = ClientAgent(
        resolved,
        ontology,
        graph,
        retriever,
        trust,
        breakers,
        providers,
        auditor,
        planner,
        bus,
        traces,
    )
    b1 = B1ToolCalling(resolved, graph, providers, planner, llm)
    b2 = B2RagOnly(resolved, graph, providers, planner, llm)
    services = AppServices(
        settings=resolved,
        cache=cache,
        traces=traces,
        trust=trust,
        breakers=breakers,
        ontology=ontology,
        graph=graph,
        retriever=retriever,
        llm=llm,
        providers=providers,
        auditor=auditor,
        mapper=mapper,
        planner=planner,
        bus=bus,
        client=client,
        b1=b1,
        b2=b2,
        platform=platform,
        knowledge=knowledge,
    )
    services.export_graph()
    return services
