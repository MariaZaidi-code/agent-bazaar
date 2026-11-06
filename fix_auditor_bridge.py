content = open('app/agents/auditor_bridge.py', 'r').read()

# Add import for LLMJudgement
content = content.replace(
    'from app.core.circuit_breaker import CircuitBreakerRegistry',
    'from app.core.circuit_breaker import CircuitBreakerRegistry\nfrom src.agent_bazaar_auditor.llm_judge import LLMJudgement'
)

# Add llm_judge parameter to __init__
old_init = '''    def __init__(
        self,
        graph: ToolKnowledgeGraph,
        trust: TrustRegistry,
        runtime_dir: Path,
        *,
        live: bool = False,
        persist: bool = True,
    ) -> None:
        self.graph = graph
        self.trust = trust
        self.live = live
        self._fallback = AuditorStub(graph, trust)
        self._lock = threading.Lock()
        self._alerts: dict[str, DriftAlertMessage] = {}
        auditor_settings = AuditorSettings(
            outputs_dir=runtime_dir / "outputs",
            cache_dir=runtime_dir / "cache",
            live=live,
            drift_mode="full",
        ).prepare()
        self.auditor = CatalogAuditor(settings=auditor_settings, persist=persist)'''

new_init = '''    def __init__(
        self,
        graph: ToolKnowledgeGraph,
        trust: TrustRegistry,
        runtime_dir: Path,
        *,
        live: bool = False,
        persist: bool = True,
        llm_judge: LLMJudgement | None = None,
    ) -> None:
        self.graph = graph
        self.trust = trust
        self.live = live
        self._fallback = AuditorStub(graph, trust)
        self._lock = threading.Lock()
        self._alerts: dict[str, DriftAlertMessage] = {}
        auditor_settings = AuditorSettings(
            outputs_dir=runtime_dir / "outputs",
            cache_dir=runtime_dir / "cache",
            live=live,
            drift_mode="full",
        ).prepare()
        self.auditor = CatalogAuditor(
            settings=auditor_settings,
            persist=persist,
            judge=llm_judge,
        )'''

assert old_init in content, "Could not find the __init__ block"
content = content.replace(old_init, new_init)

open('app/agents/auditor_bridge.py', 'w').write(content)
print('Updated app/agents/auditor_bridge.py')