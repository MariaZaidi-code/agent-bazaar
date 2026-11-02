from __future__ import annotations

import logging

from dataclasses import dataclass, field
from typing import Any

from app.agents.auditor_bridge import AuditorBridge
from app.agents.client import ClientAgent
from app.agents.mapper_stub import MapperStub
from app.agents.planner import TaskPlanner
from app.baselines.b1 import B1ToolCalling
from app.baselines.b2 import B2RagOnly
from app.config import BASE_DIR, Settings
from app.core.cache import Cache
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.jobs import JobManager
from app.core.llm import LLMClient
from app.core.message_bus import MessageBus
from app.core.tracing import TraceStore
from app.core.trust_registry import TrustRegistry
from app.core.webhooks import WebhookRegistry
from app.integration.graph_adapter import RdfToolGraph
from app.integration.mapper_adapter import KnowledgeMapper
from app.integration.ontology_bridge import KnowledgeOntology
from app.integration.runtime import KnowledgeLayer, build_knowledge_layer
from app.knowledge.graph import ToolKnowledgeGraph
from app.knowledge.ontology import Ontology
from app.knowledge.retrieval import GraphRAGRetriever
from app.mcp.registry import MCPServerRegistry
from app.platform import PlatformStore
from app.providers.registry import ProviderRegistry
from app.discovery.staging import StagingRegistry


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
    mcp: MCPServerRegistry | None = None
    webhooks: WebhookRegistry = field(default_factory=WebhookRegistry)
    jobs: JobManager = field(default_factory=JobManager)
    discovery: StagingRegistry | None = None

    def _integrate_discovered_providers(self) -> int:
        """Register verified discovery providers into the ProviderRegistry.

        This connects the discovery pipeline to the executable provider registry.
        Only VERIFIED providers are registered for execution.
        """
        if not self.discovery:
            return 0

        registered = 0
        for provider_def in self.discovery.verified():
            try:
                # Check if already registered
                if self.providers.get(provider_def.tool_id):
                    continue

                # Create a GenericProvider for this verified definition
                from app.discovery.runtime import GenericProvider

                generic_provider = GenericProvider(
                    provider_def,
                    self.settings,
                    self.cache,
                )

                # Register with the graph and validation
                self.providers.register(generic_provider)
                registered += 1
            except Exception as e:
                logging.warning("Failed to integrate provider %s: %s", provider_def.tool_id, e)

        if registered:
            logging.info("Integrated %d verified discovery providers", registered)

        return registered

    async def start_mcp(self) -> None:
        if self.mcp is None:
            return
        entries = []
        yaml_path = None
        try:
            yaml_path = self.settings.base_dir if hasattr(self.settings, "base_dir") else None
        except Exception:
            yaml_path = None
        from pathlib import Path

        candidate = self.settings.mcp_servers_file
        if not candidate.is_absolute():
            candidate = Path(__file__).resolve().parent.parent / "config" / "mcp_servers.yaml"
        if candidate.exists():
            try:
                import yaml

                data = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                servers = data.get("servers", data if isinstance(data, list) else [])
                for s in servers:
                    entries.append(s)
            except Exception:
                entries = []
        if not entries and self.settings.mcp_servers:
            for entry in self.settings.mcp_servers:
                parts = entry.split("|")
                name = parts[0].strip()
                command = parts[1].strip().split() if len(parts) > 1 else []
                entries.append({"name": name, "command": command})
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            name = str(entry.get("name", "")).strip()
            if not name:
                continue
            url = entry.get("url")
            command = entry.get("command")
            if isinstance(command, str):
                command = command.split()
            env = entry.get("env") or {}
            scopes = entry.get("scopes") or entry.get("allowed_tools")
            if not url and not command:
                continue
            try:
                self.mcp.register(name, command=command, env=env, url=url, scopes=scopes)
            except Exception:
                continue
        # per-client startup
        for name in list(self.mcp.clients.keys()):
            client = self.mcp.clients[name]
            try:
                await client.start()
            except Exception:
                continue
        from app.mcp.adapter import MCPToolProvider, mcp_tool_to_spec

        try:
            tools = await self.mcp.discover_tools()
        except Exception:
            tools = []
        for tool in tools:
            server = tool.get("_server", "")
            try:
                spec = mcp_tool_to_spec(server, tool)
            except Exception:
                continue
            try:
                self.graph.add(spec)
            except Exception:
                continue
            provider = MCPToolProvider(spec, self.settings, self.cache, self.mcp, server, tool.get("name", ""))
            try:
                self.providers.register(provider)
            except Exception:
                pass
        try:
            self.retriever.rebuild()
        except Exception:
            pass

    def export_graph(self) -> bool:
        trust = {item["provider_id"]: item for item in self.trust.all()}
        return self.graph.export_turtle(self.settings.runtime_dir / "knowledge_graph.ttl", trust=trust)

    def export_graph_jsonld(self) -> bool:
        trust = {item["provider_id"]: item for item in self.trust.all()}
        path = self.settings.runtime_dir / "knowledge_graph.jsonld"
        if hasattr(self.graph, "export_jsonld"):
            try:
                return bool(self.graph.export_jsonld(path, trust=trust))
            except TypeError:
                return bool(self.graph.export_jsonld(path))
        return False

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
                    "failure_mode": ("offline" if (self.settings.offline_mode or provider.offline_forced) else "live"),
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

    def shutdown(self) -> None:
        self.jobs.shutdown()


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
    planner = TaskPlanner(ontology, llm, resolved)
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
    from app.discovery.staging import StagingRegistry as _StagingRegistry

    mcp_registry = MCPServerRegistry()
    discovery_registry = _StagingRegistry(
        staging_dir=resolved.runtime_dir / "discovery" / "staging",
        specs_dir=BASE_DIR / "data" / "specs",
        overrides_path=BASE_DIR / "data" / "overrides" / "pricing.yaml",
    )
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
        mcp=mcp_registry,
        discovery=discovery_registry,
    )

    services.export_graph()
    services.export_graph_jsonld()

    # Integrate any verified discovery providers
    if services.discovery:
        services._integrate_discovered_providers()

    return services
