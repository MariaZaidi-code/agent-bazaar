from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from app.agents import ranking_policy
from app.agents.auditor_stub import AuditorStub
from app.agents.planner import TaskPlanner
from app.agents.ranking_policy import CandidateFacts, RankedCandidate, RankingPolicy
from app.config import Settings
from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.message_bus import MessageBus
from app.core.tracing import TraceStore
from app.core.trust_registry import TrustRegistry
from app.knowledge.graph import ToolKnowledgeGraph
from app.knowledge.ontology import Ontology
from app.knowledge.retrieval import GraphRAGRetriever
from app.providers.base import ProviderResponse
from app.providers.registry import ProviderRegistry
from app.schemas import (
    BaseMessage,
    BreakerStatus,
    Candidate,
    CandidateList,
    ClaimLabel,
    ExecutionPlan,
    FeedbackMessage,
    LinkCheck,
    PlanStep,
    ServiceCallMessage,
    ServiceResultMessage,
    StepStatus,
    SubGoal,
    SubstituteRequestMessage,
    TaskMetrics,
    TaskRequestMessage,
    TaskResult,
    TaskStatus,
    ToolSpec,
    TraceEvent,
    TrustUpdateMessage,
    VerifyRequestMessage,
    new_id,
)

SLOT_CONCEPTS = {
    "location": "LocationName",
    "country": "CountryName",
    "country_code": "CountryCode",
    "year": "Number",
    "amount": "MoneyAmount",
    "from_currency": "CurrencyCode",
    "to_currency": "CurrencyCode",
    "date": "DateTimeISO",
    "query": "ResearchTopic",
    "document_id": "DocumentReference",
    "news_query": "NewsTopic",
    "show_query": "ShowQuery",
    "book_query": "BookQuery",
    "recipe_query": "RecipeQuery",
    "asset": "CryptoAsset",
    "currency": "CurrencyCode",
    "text": "Text",
    "source_language": "LanguageCode",
    "target_language": "LanguageCode",
    "timezone": "TimezoneName",
    "league": "SportsLeague",
}

CAPABILITY_LABELS = {
    "GeocodeLocation": "location",
    "GetWeatherForecast": "weather",
    "ConvertCurrency": "currency",
    "GetCountryFacts": "country",
    "GetPublicHolidays": "holidays",
    "SearchResearchPapers": "research",
    "QueryStructuredData": "database",
    "AnswerFromDocument": "document",
    "SearchNews": "news",
    "GetCryptoPrice": "crypto",
    "SearchTVShows": "television",
    "SearchBooks": "books",
    "TranslateText": "translation",
    "GetCurrentTime": "time",
    "GetSunTimes": "sun",
    "SearchRecipes": "recipes",
    "GetSportsScores": "sports",
}


class ClientAgent:
    def __init__(
        self,
        settings: Settings,
        ontology: Ontology,
        graph: ToolKnowledgeGraph,
        retriever: GraphRAGRetriever,
        trust: TrustRegistry,
        breakers: CircuitBreakerRegistry,
        providers: ProviderRegistry,
        auditor: AuditorStub,
        planner: TaskPlanner,
        bus: MessageBus,
        traces: TraceStore,
    ) -> None:
        self.settings = settings
        self.ontology = ontology
        self.graph = graph
        self.retriever = retriever
        self.trust = trust
        self.breakers = breakers
        self.providers = providers
        self.auditor = auditor
        self.planner = planner
        self.bus = bus
        self.traces = traces

    def ranking_policy(self) -> RankingPolicy:
        """Build the free-first ranking policy from the settings."""
        tier_order = list(self.settings.tier_order)
        if "unknown" not in tier_order:
            tier_order.append("unknown")
        return RankingPolicy(
            pricing_policy=self.settings.pricing_policy,
            tier_order=tuple(tier_order),
            doc_quality_weight=self.settings.doc_quality_weight,
            mapping_coverage_weight=self.settings.mapping_coverage_weight,
            chain_fit_weight=self.settings.chain_fit_weight,
            latency_weight=self.settings.latency_weight,
            freshness_weight=self.settings.freshness_weight,
            latency_normalizer_ms=self.settings.latency_normalizer_ms,
            freshness_half_life_days=self.settings.freshness_half_life_days,
            min_rating_count=self.settings.min_rating_count,
            rating_floor=self.settings.rating_floor,
            contradicted_penalty=self.settings.contradicted_penalty,
            require_known_licence=self.settings.require_known_licence,
        )

    async def run(self, task: str, document_id: str | None = None) -> TaskResult:
        task_id = new_id("task")
        started = time.perf_counter()
        self._trace(
            task_id,
            "task_started",
            "client",
            "Task received by the Client agent.",
            {"task": task, "mode": self._mode(), "document_id": document_id},
        )
        try:
            result = await self._run(task_id, task, started, document_id=document_id)
        except Exception as exc:
            self._trace(
                task_id,
                "task_error",
                "client",
                f"Task failed: {exc}",
                {"error": str(exc)},
            )
            result = TaskResult(
                task_id=task_id,
                task=task,
                status=TaskStatus.failed,
                error=str(exc),
                answer=f"I could not complete the task: {exc}",
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
                mode=self._mode(),
            )
        result.trace = self.traces.events(task_id)
        result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        self.traces.save_result(result)
        return result

    async def _run(
        self,
        task_id: str,
        task: str,
        started: float,
        document_id: str | None = None,
    ) -> TaskResult:
        metrics = TaskMetrics()
        await self._publish(
            TaskRequestMessage(
                sender="interface",
                recipient="client",
                correlation_id=task_id,
                task_id=task_id,
                task=task,
            ),
            task_id,
        )
        for alert in self.auditor.alerts():
            if self.settings.use_circuit_breaker:
                provider = self.graph.get(alert.tool_id)
                if provider is not None:
                    key = self.breakers.link_key("client", provider.provider_id)
                    self.breakers.trip(key, f"drift alert {alert.alert_id}")
            self._trace(
                task_id,
                "drift_alert",
                "auditor",
                f"Drift alert for {alert.tool_id}.",
                alert.model_dump(mode="json"),
            )

        plan_started = time.perf_counter()
        subgoals, warnings = await self.planner.decompose(task, correlation_id=task_id)
        if document_id:
            for subgoal in subgoals:
                if subgoal.capability == "AnswerFromDocument":
                    subgoal.slots["document_id"] = document_id
        metrics.tokens = 0
        subgoal_map = {subgoal.id: subgoal for subgoal in subgoals}
        self._trace(
            task_id,
            "task_decomposed",
            "client",
            f"Task decomposed into {len(subgoals)} sub-goal(s).",
            {"subgoals": [item.model_dump(mode="json") for item in subgoals]},
        )

        candidate_lists: list[CandidateList] = []
        for subgoal in subgoals:
            candidate_list = await self._candidates(
                task_id, task, subgoal, subgoals, metrics
            )
            candidate_lists.append(candidate_list)
        self._trace(
            task_id,
            "planning_finished",
            "client",
            "Task decomposition and candidate matching finished.",
            {"elapsed_ms": round((time.perf_counter() - plan_started) * 1000, 2)},
        )

        composition_started = time.perf_counter()
        plan, composition_errors = self._compose(task_id, subgoals, candidate_lists, subgoal_map)
        metrics.composition_ms = round((time.perf_counter() - composition_started) * 1000, 2)
        self._trace(
            task_id,
            "chain_composed",
            "client",
            (
                "A valid execution chain was composed."
                if plan.valid
                else "Chain composition failed; no tool call was made."
            ),
            {
                "valid": plan.valid,
                "steps": [step.model_dump(mode="json") for step in plan.steps],
                "errors": composition_errors,
            },
        )
        if not plan.valid:
            result = TaskResult(
                task_id=task_id,
                task=task,
                status=TaskStatus.failed,
                subgoals=subgoals,
                candidate_lists=candidate_lists,
                plan=plan,
                warnings=warnings,
                answer="I could not build a valid chain. " + " ".join(composition_errors),
                mode=self._mode(),
                metrics=metrics,
                error="; ".join(composition_errors),
            )
            self._trace(
                task_id,
                "task_completed",
                "client",
                "Task failed during composition.",
                {"status": result.status.value, "errors": composition_errors},
            )
            return result

        execution_started = time.perf_counter()
        step_failures = await self._execute_plan(
            task_id,
            task,
            subgoals,
            subgoal_map,
            plan,
            metrics,
            warnings,
        )
        metrics.execution_ms = round((time.perf_counter() - execution_started) * 1000, 2)

        completed = [
            step
            for step in plan.steps
            if step.status in {StepStatus.completed, StepStatus.substituted}
        ]
        if not step_failures:
            status = TaskStatus.completed
        elif completed:
            status = TaskStatus.partial
        else:
            status = TaskStatus.failed
        answer = self._synthesize_answer(plan, status, step_failures)
        result = TaskResult(
            task_id=task_id,
            task=task,
            status=status,
            answer=answer,
            subgoals=subgoals,
            candidate_lists=candidate_lists,
            plan=plan,
            warnings=self._dedupe(warnings),
            mode=self._mode(plan),
            metrics=metrics,
            error="; ".join(step_failures) if step_failures else None,
        )
        result.metrics.total_ms = round((time.perf_counter() - started) * 1000, 2)
        self._trace(
            task_id,
            "task_completed",
            "client",
            f"Task finished with status {status.value}.",
            {
                "status": status.value,
                "answer": answer,
                "failures": step_failures,
                "metrics": result.metrics.model_dump(mode="json"),
                "mode": result.mode,
            },
        )
        return result

    async def _candidates(
        self,
        task_id: str,
        task: str,
        subgoal: SubGoal,
        subgoals: list[SubGoal],
        metrics: TaskMetrics,
    ) -> CandidateList:
        retrieval_started = time.perf_counter()
        query = " ".join(
            [subgoal.description, *[str(value) for value in subgoal.slots.values()]]
        )
        retrieved = self.retriever.search(
            query,
            top_k=self.settings.ranking_top_k,
            capability=subgoal.capability,
            expand=True,
        )
        metrics.retrieval_ms += (time.perf_counter() - retrieval_started) * 1000
        available = self._available_concepts(subgoal, subgoals)
        candidates: list[Candidate] = []
        filtered: list[dict[str, Any]] = []
        for tool, relevance, reasons in retrieved:
            if tool.capability != subgoal.capability:
                filtered.append({"tool_id": tool.id, "reason": "capability mismatch"})
                continue
            violations = self.providers.validation.get(tool.id, [])
            if violations:
                filtered.append({"tool_id": tool.id, "reason": "; ".join(violations)})
                continue
            if self.settings.use_ontology:
                filter_reason = self._ontology_filter_reason(tool, subgoal, available)
                if filter_reason:
                    filtered.append({"tool_id": tool.id, "reason": filter_reason})
                    continue
            candidates.append(
                Candidate(
                    tool=tool,
                    relevance=round(max(0.35, relevance), 4),
                    reasons=[
                        *reasons,
                        f"capability {subgoal.capability} matched",
                        "typed inputs fit the sub-goal"
                        if self.settings.use_ontology
                        else "ontology filter disabled (ablation)",
                    ],
                )
            )
        if self.settings.use_auditor and candidates:
            verify_started = time.perf_counter()
            await self._publish(
                VerifyRequestMessage(
                    sender="client",
                    recipient="auditor",
                    correlation_id=task_id,
                    task_id=task_id,
                    subgoal_id=subgoal.id,
                    candidates=candidates,
                ),
                task_id,
            )
            verification = await self.auditor.verify(
                task_id, subgoal.id, candidates, correlation_id=task_id
            )
            await self._publish(verification, task_id)
            metrics.verification_ms += (time.perf_counter() - verify_started) * 1000
            for candidate in candidates:
                candidate.claim_label = verification.overall.get(
                    candidate.tool.id, ClaimLabel.unsupported
                )
            for alert_id in verification.drift_alerts:
                self._trace(
                    task_id,
                    "drift_alert",
                    "auditor",
                    f"Auditor reported drift alert {alert_id}.",
                    {"alert_id": alert_id, "subgoal_id": subgoal.id},
                )
            self._trace(
                task_id,
                "claims_verified",
                "auditor",
                "Claim labels returned for the candidate list.",
                {
                    "subgoal_id": subgoal.id,
                    "overall": {
                        key: value.value for key, value in verification.overall.items()
                    },
                },
            )
        else:
            for candidate in candidates:
                candidate.claim_label = ClaimLabel.unsupported
            self._trace(
                task_id,
                "claims_verified",
                "auditor",
                "Verification skipped for this ablation.",
                {"subgoal_id": subgoal.id, "count": len(candidates)},
            )

        for candidate in candidates:
            provider_id = candidate.tool.provider_id
            trust_state = (
                self.trust.get(provider_id)
                if self.settings.use_trust
                else {"score": 0.5, "demoted": False}
            )
            candidate.trust = round(float(trust_state["score"]), 4)
            candidate.demoted = bool(trust_state.get("demoted", False))
            key = self.breakers.link_key("client", provider_id)
            candidate.breaker_state = self.breakers.state(key)
            candidate.reasons.append(f"claim label {candidate.claim_label.value}")
        policy = self.ranking_policy()
        facts = self.candidate_facts(candidates, subgoal, subgoals)
        candidates = self._apply_policy(candidates, facts, policy)
        for rank, candidate in enumerate(candidates, start=1):
            candidate.rank = rank
        candidate_list = CandidateList(
            sender="client",
            recipient="interface",
            correlation_id=task_id,
            task_id=task_id,
            subgoal_id=subgoal.id,
            capability=subgoal.capability,
            candidates=candidates,
        )
        await self._publish(candidate_list, task_id)
        self._trace(
            task_id,
            "graphrag_shortlist",
            "client",
            f"Retrieved {len(retrieved)} candidate(s) for {subgoal.capability}; "
            f"{len(candidates)} survived the filter.",
            {
                "subgoal_id": subgoal.id,
                "query": query,
                "retrieved": [
                    {"tool_id": tool.id, "relevance": relevance, "reasons": reasons}
                    for tool, relevance, reasons in retrieved
                ],
                "filtered": filtered,
                "free_first_compliance": ranking_policy.free_first_compliance(
                    facts, policy
                ),
                "policy": {
                    "pricing_policy": policy.pricing_policy,
                    "tier_order": list(policy.tier_order),
                    "doc_quality_weight": policy.doc_quality_weight,
                    "mapping_coverage_weight": policy.mapping_coverage_weight,
                    "chain_fit_weight": policy.chain_fit_weight,
                    "min_rating_count": policy.min_rating_count,
                    "rating_floor": policy.rating_floor,
                    "contradicted_penalty": policy.contradicted_penalty,
                    "require_known_licence": policy.require_known_licence,
                },
                "ranked": [
                    {
                        "tool_id": item.tool.id,
                        "name": item.tool.name,
                        "pricing_tier": item.tool.pricing_tier,
                        "access_requirement": item.tool.access_requirement,
                        "score": item.score,
                        "relevance": item.relevance,
                        "trust": item.trust,
                        "claim_label": item.claim_label.value,
                        "eligible": item.eligible,
                        "executable": self._executable(item.tool, policy),
                        "breaker": item.breaker_state.value,
                        "reasons": item.reasons,
                    }
                    for item in candidates
                ],
            },
        )
        self._trace(
            task_id,
            "candidate_ranking",
            "client",
            f"Ranked {len(candidates)} candidate(s) for {subgoal.capability}.",
            {
                "subgoal_id": subgoal.id,
                "ranked": [
                    {
                        "tool_id": item.tool.id,
                        "name": item.tool.name,
                        "score": item.score,
                        "relevance": item.relevance,
                        "trust": item.trust,
                        "pricing_tier": item.tool.pricing_tier,
                        "executable": self._executable(item.tool, policy),
                        "claim_label": item.claim_label.value,
                        "eligible": item.eligible,
                        "breaker": item.breaker_state.value,
                    }
                    for item in candidates
                ],
            },
        )
        return candidate_list

    def rank_candidates(
        self,
        candidates: list[Candidate],
        subgoal: SubGoal,
        subgoals: list[SubGoal],
        policy: RankingPolicy | None = None,
    ) -> list[Candidate]:
        """Rank the candidates free-first and attach the policy reasons to them."""
        policy = policy or self.ranking_policy()
        facts = self.candidate_facts(candidates, subgoal, subgoals)
        return self._apply_policy(candidates, facts, policy)

    def candidate_facts(
        self,
        candidates: list[Candidate],
        subgoal: SubGoal,
        subgoals: list[SubGoal],
    ) -> list[CandidateFacts]:
        """Collect the stored facts the ranking policy weighs for the candidates."""
        return [
            self._candidate_facts(candidate, subgoal, subgoals) for candidate in candidates
        ]

    def _apply_policy(
        self,
        candidates: list[Candidate],
        facts: list[CandidateFacts],
        policy: RankingPolicy,
    ) -> list[Candidate]:
        """Sort the candidates with the policy and attach the policy reasons to them."""
        ranked = ranking_policy.rank_candidates(facts, policy)
        by_id = {candidate.tool.id: candidate for candidate in candidates}
        ordered: list[Candidate] = []
        for item in ranked:
            candidate = by_id[item.tool_id]
            score = item.score
            eligible = item.eligible
            if (
                self.settings.use_auditor
                and self.settings.exclude_contradicted
                and candidate.claim_label == ClaimLabel.contradicted
            ):
                score = 0.0
                eligible = False
            candidate.score = score
            candidate.eligible = eligible
            candidate.reasons = self._policy_reasons(candidate, item, policy)
            ordered.append(candidate)
        return ordered

    def _candidate_facts(
        self,
        candidate: Candidate,
        subgoal: SubGoal,
        subgoals: list[SubGoal],
    ) -> CandidateFacts:
        """Collect the stored facts the ranking policy weighs for one candidate."""
        tool = candidate.tool
        if self._has_profile(tool):
            doc_quality = tool.doc_quality
            mapping_coverage = tool.mapping_coverage
            chain_fit = self._chain_fit(tool, subgoal, subgoals)
        else:
            doc_quality = 1.0
            mapping_coverage = 1.0
            chain_fit = 1.0
        return CandidateFacts(
            tool_id=tool.id,
            relevance=candidate.relevance,
            trust=candidate.trust,
            pricing_tier=tool.pricing_tier,
            access_requirement=tool.access_requirement,
            rating_value=tool.rating_value,
            rating_count=tool.rating_count,
            doc_quality=doc_quality,
            mapping_coverage=mapping_coverage,
            chain_fit=chain_fit,
            latency_ms=tool.latency_ms,
            freshness_days=tool.freshness_days,
            claim_label=candidate.claim_label.value.lower(),
            demoted=bool(candidate.demoted) and self.settings.use_trust,
            breaker_open=(
                self.settings.use_circuit_breaker
                and candidate.breaker_state == BreakerStatus.open
            ),
            licence=tool.licence,
        )

    def _policy_reasons(
        self,
        candidate: Candidate,
        item: RankedCandidate,
        policy: RankingPolicy,
    ) -> list[str]:
        """Combine the retrieval reasons with the reasons of the ranking policy."""
        reasons = list(candidate.reasons)
        executable = self._executable(candidate.tool, policy)
        for reason in item.reasons:
            if executable and reason.startswith("not executable:"):
                continue
            reasons.append(reason)
        if not executable and not any(
            reason.startswith("not executable:") for reason in reasons
        ):
            reasons.append(self._not_executable_reason(candidate.tool))
        if (
            self.settings.use_auditor
            and self.settings.exclude_contradicted
            and candidate.claim_label == ClaimLabel.contradicted
        ):
            reasons.append("contradicted tools excluded by configuration")
        return reasons

    def _chain_fit(
        self,
        tool: ToolSpec,
        subgoal: SubGoal,
        subgoals: list[SubGoal],
    ) -> float:
        """Share of the required inputs the chain can supply for this tool."""
        required = [item for item in tool.inputs if item.required]
        if not required:
            return 1.0
        available = self._available_concepts(subgoal, subgoals)
        satisfied = 0
        for item in required:
            if item.name in subgoal.slots:
                satisfied += 1
                continue
            if any(
                self.ontology.check_link(concept, None, item.concept, None).valid
                for concept in available
            ):
                satisfied += 1
        return round(satisfied / len(required), 6)

    def _executable(self, tool: ToolSpec, policy: RankingPolicy) -> bool:
        """Free and keyless tools may run; a tool without a profile keeps the old behaviour."""
        if not self._has_profile(tool):
            return True
        facts = CandidateFacts(
            tool_id=tool.id,
            pricing_tier=tool.pricing_tier,
            access_requirement=tool.access_requirement,
            licence=tool.licence,
        )
        return ranking_policy.is_executable(facts, policy)

    @staticmethod
    def _has_profile(tool: ToolSpec) -> bool:
        """True when the tool carries a curated commercial profile."""
        return tool.pricing_tier != "unknown" or tool.access_requirement != "unknown"

    @staticmethod
    def _not_executable_reason(tool: ToolSpec) -> str:
        """The reason a tool is not executed, as the policy words it."""
        if tool.pricing_tier != "free":
            return f"not executable: {tool.pricing_tier} tier"
        return "not executable: requires an api key"

    def _compose(
        self,
        task_id: str,
        subgoals: list[SubGoal],
        candidate_lists: list[CandidateList],
        subgoal_map: dict[str, SubGoal],
    ) -> tuple[ExecutionPlan, list[str]]:
        plan = ExecutionPlan(task_id=task_id)
        errors: list[str] = []
        ordered = self._topological_order(subgoals)
        candidates_by_subgoal = {item.subgoal_id: item.candidates for item in candidate_lists}
        steps_by_subgoal: dict[str, PlanStep] = {}
        policy = self.ranking_policy()
        for subgoal in ordered:
            candidates = candidates_by_subgoal.get(subgoal.id, [])
            eligible = [
                item
                for item in candidates
                if item.eligible and self._executable(item.tool, policy)
            ]
            if not eligible:
                reason = (
                    f"No eligible tool for {subgoal.capability}. "
                    "Every candidate was filtered, demoted, blocked by an open breaker "
                    "or is not executable."
                )
                errors.append(reason)
                step = PlanStep(
                    id=subgoal.id,
                    subgoal_id=subgoal.id,
                    tool_id="",
                    tool_name="No eligible tool",
                    capability=subgoal.capability,
                    branch=subgoal.branch,
                    status=StepStatus.skipped,
                    error=reason,
                )
                plan.steps.append(step)
                steps_by_subgoal[subgoal.id] = step
                plan.branches.setdefault(subgoal.branch, []).append(step.id)
                continue
            selected: Candidate | None = None
            selected_bindings: dict[str, str] = {}
            selected_checks: list[LinkCheck] = []
            rejected: list[dict[str, Any]] = [
                {
                    "tool_id": item.tool.id,
                    "binding_errors": [],
                    "link_errors": [],
                    "reason": self._not_executable_reason(item.tool),
                }
                for item in candidates
                if not self._executable(item.tool, policy)
            ]
            for candidate in eligible:
                dependency_steps = [
                    steps_by_subgoal[dep]
                    for dep in subgoal.depends_on
                    if dep in steps_by_subgoal
                ]
                bindings, binding_errors = self._build_bindings(
                    candidate.tool, subgoal, dependency_steps
                )
                checks = (
                    self._link_checks(candidate.tool, subgoal, dependency_steps)
                    if self.settings.use_ontology
                    else []
                )
                check_errors = [check.reason for check in checks if not check.valid]
                if not binding_errors and not check_errors:
                    selected = candidate
                    selected_bindings = bindings
                    selected_checks = checks
                    break
                rejected.append(
                    {
                        "tool_id": candidate.tool.id,
                        "binding_errors": binding_errors,
                        "link_errors": check_errors,
                    }
                )
            if selected is None:
                first = eligible[0]
                dependency_steps = [
                    steps_by_subgoal[dep]
                    for dep in subgoal.depends_on
                    if dep in steps_by_subgoal
                ]
                bindings, binding_errors = self._build_bindings(
                    first.tool, subgoal, dependency_steps
                )
                checks = self._link_checks(first.tool, subgoal, dependency_steps)
                reason = (
                    f"No candidate for {subgoal.capability} passed type/unit and input checks."
                )
                errors.append(reason)
                step = PlanStep(
                    id=subgoal.id,
                    subgoal_id=subgoal.id,
                    tool_id=first.tool.id,
                    tool_name=first.tool.name,
                    capability=subgoal.capability,
                    branch=subgoal.branch,
                    input_bindings=bindings,
                    link_checks=checks,
                    status=StepStatus.skipped,
                    error=reason,
                )
                plan.steps.append(step)
                steps_by_subgoal[subgoal.id] = step
                plan.branches.setdefault(subgoal.branch, []).append(step.id)
                self._trace(
                    task_id,
                    "link_rejected",
                    "client",
                    f"Rejected all candidates for {subgoal.capability}.",
                    {"rejected": rejected},
                )
                continue
            step = PlanStep(
                id=subgoal.id,
                subgoal_id=subgoal.id,
                tool_id=selected.tool.id,
                tool_name=selected.tool.name,
                capability=subgoal.capability,
                branch=subgoal.branch,
                input_bindings=selected_bindings,
                link_checks=selected_checks,
            )
            plan.steps.append(step)
            steps_by_subgoal[subgoal.id] = step
            plan.branches.setdefault(subgoal.branch, []).append(step.id)
        plan.valid = not errors
        plan.errors = errors
        return plan, errors

    async def _execute_plan(
        self,
        task_id: str,
        task: str,
        subgoals: list[SubGoal],
        subgoal_map: dict[str, SubGoal],
        plan: ExecutionPlan,
        metrics: TaskMetrics,
        warnings: list[str],
    ) -> list[str]:
        outputs: dict[str, dict[str, Any]] = {}
        failures: list[str] = []
        stopped = False
        for step in plan.steps:
            if stopped:
                step.status = StepStatus.skipped
                step.error = "Skipped because an earlier step failed."
                continue
            subgoal = subgoal_map[step.subgoal_id]
            if not step.tool_id:
                step.status = StepStatus.failed
                step.error = "No eligible tool was selected."
                failures.append(step.error)
                stopped = True
                continue
            try:
                params = self._resolve_bindings(
                    step.input_bindings, subgoal, outputs
                )
            except Exception as exc:
                step.status = StepStatus.failed
                step.error = f"Could not bind inputs: {exc}"
                failures.append(step.error)
                stopped = True
                continue
            step.params = params
            self._trace(
                task_id,
                "step_started",
                "client",
                f"Calling {step.tool_name} for {step.capability}.",
                {
                    "step_id": step.id,
                    "tool_id": step.tool_id,
                    "params": params,
                    "input_bindings": step.input_bindings,
                },
            )
            response, call_error = await self._call_tool(
                task_id, step, params
            )
            if response is not None and response.status == "success" and response.schema_valid:
                await self._finish_success(
                    task_id, step, response, outputs, metrics, warnings
                )
                continue
            reason = call_error or (response.error if response else "unknown call failure")
            if response is not None and response.status == "success" and not response.schema_valid:
                reason = "schema invalid: " + "; ".join(response.schema_errors)
            await self._record_outcome(
                task_id, step, response, call_attempted=response is not None
            )
            self._trace(
                task_id,
                "step_failed",
                "provider",
                f"{step.tool_name} failed: {reason}",
                {
                    "step_id": step.id,
                    "tool_id": step.tool_id,
                    "reason": reason,
                    "source": response.source if response else "breaker",
                },
            )
            recovered = await self._recover(
                task_id,
                step,
                subgoal,
                subgoals,
                plan,
                outputs,
                metrics,
                warnings,
                reason,
            )
            if recovered:
                continue
            step.status = StepStatus.failed
            step.error = reason
            failures.append(f"{step.capability}: {reason}")
            stopped = True
        return failures

    async def _call_tool(
        self,
        task_id: str,
        step: PlanStep,
        params: dict[str, Any],
    ) -> tuple[ProviderResponse | None, str | None]:
        provider = self.providers.by_tool(step.tool_id)
        if provider is None:
            return None, f"No provider implementation for {step.tool_id}"
        key = self.breakers.link_key("client", provider.provider_id)
        if self.settings.use_circuit_breaker:
            allowed, state = self.breakers.allow(key)
            if not allowed:
                return None, f"circuit breaker is {state.value} for {provider.provider_id}"
        await self._publish(
            ServiceCallMessage(
                sender="client",
                recipient=provider.provider_id,
                correlation_id=task_id,
                task_id=task_id,
                step_id=step.id,
                tool_id=step.tool_id,
                params=params,
            ),
            task_id,
        )
        response = await provider.call(params, correlation_id=task_id)
        await self._publish(
            ServiceResultMessage(
                sender=provider.provider_id,
                recipient="client",
                correlation_id=task_id,
                task_id=task_id,
                step_id=step.id,
                tool_id=step.tool_id,
                status=response.status,
                data=response.data,
                error=response.error,
                latency_ms=response.latency_ms,
                cached=response.cached,
                source=response.source,
            ),
            task_id,
        )
        return response, None

    async def _finish_success(
        self,
        task_id: str,
        step: PlanStep,
        response: ProviderResponse,
        outputs: dict[str, dict[str, Any]],
        metrics: TaskMetrics,
        warnings: list[str],
    ) -> None:
        step.output = response.data
        step.latency_ms = response.latency_ms
        step.cached = response.cached
        step.source = response.source
        step.status = (
            StepStatus.substituted
            if step.substituted_from
            else StepStatus.completed
        )
        step.error = None
        outputs[step.id] = response.data
        if response.warning:
            warnings.append(response.warning)
        await self._record_outcome(task_id, step, response, call_attempted=True)
        self._trace(
            task_id,
            "step_succeeded",
            "provider",
            f"{step.tool_name} returned a schema-valid result.",
            {
                "step_id": step.id,
                "tool_id": step.tool_id,
                "status": step.status.value,
                "source": response.source,
                "cached": response.cached,
                "latency_ms": response.latency_ms,
                "output": response.data,
                "substituted_from": step.substituted_from,
            },
        )
        await self._publish(
            FeedbackMessage(
                sender="client",
                recipient="mapper,auditor",
                correlation_id=task_id,
                task_id=task_id,
                tool_id=step.tool_id,
                outcome="success",
                schema_valid=True,
            ),
            task_id,
        )

    async def _record_outcome(
        self,
        task_id: str,
        step: PlanStep,
        response: ProviderResponse | None,
        call_attempted: bool,
    ) -> None:
        provider = self.providers.by_tool(step.tool_id)
        if provider is None:
            return
        provider_id = provider.provider_id
        key = self.breakers.link_key("client", provider_id)
        success = bool(
            response
            and response.status == "success"
            and response.schema_valid
        )
        if self.settings.use_circuit_breaker:
            if success:
                self.breakers.record_success(key, "call returned a schema-valid result")
            elif call_attempted:
                self.breakers.record_failure(
                    key,
                    response.error if response and response.error else "schema validation failed",
                )
        if not self.settings.use_feedback:
            return
        if call_attempted and response is not None:
            call_success = response.status == "success"
            self.trust.record_call(
                provider_id,
                call_success,
                reason=f"service call for {step.subgoal_id} ({step.tool_id})",
                source="execution",
            )
            await self._publish_trust_update(
                task_id,
                provider_id,
                "call",
                call_success,
                f"service call for {step.tool_id}",
            )
            if call_success:
                schema_success = response.schema_valid
                self.trust.record_schema(
                    provider_id,
                    schema_success,
                    reason=f"schema validation for {step.tool_id}",
                    source="execution",
                )
                await self._publish_trust_update(
                    task_id,
                    provider_id,
                    "schema",
                    schema_success,
                    f"schema validation for {step.tool_id}",
                )

    async def _publish_trust_update(
        self,
        task_id: str,
        provider_id: str,
        signal: str,
        success: bool,
        reason: str,
    ) -> None:
        message = TrustUpdateMessage(
            sender="execution-log",
            recipient="trust-registry",
            correlation_id=task_id,
            provider_id=provider_id,
            signal=signal,
            success=success,
            reason=reason,
            source="client",
        )
        await self.bus.publish(message, task_id)

    async def _recover(
        self,
        task_id: str,
        step: PlanStep,
        subgoal: SubGoal,
        subgoals: list[SubGoal],
        plan: ExecutionPlan,
        outputs: dict[str, dict[str, Any]],
        metrics: TaskMetrics,
        warnings: list[str],
        reason: str,
    ) -> bool:
        if not self.settings.use_substitution:
            return False
        substitution_started = time.perf_counter()
        original_tool = step.tool_id
        available = self._available_concepts(subgoal, subgoals)
        candidates = self.graph.compatible_substitutes(
            subgoal.capability,
            available,
            None,
            exclude={original_tool, step.tool_id},
        )
        evaluated: list[tuple[float, ToolSpec]] = []
        policy = self.ranking_policy()
        for tool in candidates:
            if tool.id == original_tool:
                continue
            provider = self.providers.by_tool(tool.id)
            if provider is None:
                continue
            if not self._executable(tool, policy):
                continue
            if self.settings.use_auditor and ClaimLabel.contradicted in tool.claim_labels():
                continue
            trust_state = self.trust.get(tool.provider_id) if self.settings.use_trust else {
                "score": 0.5,
                "demoted": False,
            }
            if self.settings.use_trust and trust_state.get("demoted"):
                continue
            if self.settings.use_circuit_breaker:
                state = self.breakers.state(
                    self.breakers.link_key("client", tool.provider_id)
                )
                if state == BreakerStatus.open:
                    continue
            score = self._substitution_score(tool, available, None, trust_state)
            evaluated.append((score, tool))
        evaluated.sort(key=lambda item: (-item[0], item[1].id))
        self._trace(
            task_id,
            "substitution_requested",
            "client",
            f"Looking for a compatible substitute for {original_tool}.",
            {
                "step_id": step.id,
                "failed_tool": original_tool,
                "reason": reason,
                "candidates": [tool.id for _, tool in evaluated],
            },
        )
        dependency_steps = self._dependency_steps(plan, subgoal)
        for _, tool in evaluated:
            bindings, binding_errors = self._build_bindings(tool, subgoal, dependency_steps)
            checks = (
                self._link_checks(tool, subgoal, dependency_steps)
                if self.settings.use_ontology
                else []
            )
            check_errors = [check.reason for check in checks if not check.valid]
            if binding_errors or check_errors:
                self._trace(
                    task_id,
                    "substitute_rejected",
                    "client",
                    f"Substitute {tool.id} failed type/unit checks.",
                    {
                        "tool_id": tool.id,
                        "binding_errors": binding_errors,
                        "link_errors": check_errors,
                    },
                )
                continue
            try:
                params = self._resolve_bindings(bindings, subgoal, outputs)
            except Exception as exc:
                self._trace(
                    task_id,
                    "substitute_rejected",
                    "client",
                    f"Substitute {tool.id} could not be bound: {exc}",
                    {"tool_id": tool.id},
                )
                continue
            await self._publish(
                SubstituteRequestMessage(
                    sender="client",
                    recipient="client",
                    correlation_id=task_id,
                    task_id=task_id,
                    step_id=step.id,
                    failed_tool_id=original_tool,
                    capability=subgoal.capability,
                    chosen_tool_id=tool.id,
                    reason=reason,
                ),
                task_id,
            )
            step.substituted_from = original_tool
            step.tool_id = tool.id
            step.tool_name = tool.name
            step.input_bindings = bindings
            step.link_checks = checks
            step.params = params
            step.error = None
            self._trace(
                task_id,
                "substitute_selected",
                "client",
                f"Substituting {tool.name} for {original_tool}.",
                {
                    "step_id": step.id,
                    "tool_id": tool.id,
                    "failed_tool": original_tool,
                    "params": params,
                },
            )
            response, call_error = await self._call_tool(task_id, step, params)
            if response is not None and response.status == "success" and response.schema_valid:
                await self._finish_success(
                    task_id, step, response, outputs, metrics, warnings
                )
                metrics.substitution_ms += (
                    time.perf_counter() - substitution_started
                ) * 1000
                self._trace(
                    task_id,
                    "substitution_succeeded",
                    "client",
                    f"Chain recovered with substitute {tool.id}.",
                    {"step_id": step.id, "tool_id": tool.id},
                )
                return True
            failure_reason = call_error or (
                response.error if response else "substitute call failed"
            )
            await self._record_outcome(
                task_id, step, response, call_attempted=response is not None
            )
            self._trace(
                task_id,
                "substitute_failed",
                "provider",
                f"Substitute {tool.id} failed: {failure_reason}",
                {"step_id": step.id, "tool_id": tool.id, "reason": failure_reason},
            )
        metrics.substitution_ms += (time.perf_counter() - substitution_started) * 1000
        return False

    @staticmethod
    def _dependency_steps(plan: ExecutionPlan, subgoal: SubGoal) -> list[PlanStep]:
        by_id = {step.id: step for step in plan.steps}
        return [
            by_id[dep_id]
            for dep_id in subgoal.depends_on
            if dep_id in by_id
        ]

    def _substitution_score(
        self,
        tool: ToolSpec,
        available_inputs: list[str],
        available_outputs: list[str] | None,
        trust_state: dict[str, Any],
    ) -> float:
        """Score how safely and usefully a candidate can replace a failed tool."""
        required = [item.concept for item in tool.inputs if item.required]
        if required:
            satisfied = sum(
                1
                for concept in required
                if any(self.ontology.check_link(available, None, concept, None).valid for available in available_inputs)
            )
            input_score = satisfied / len(required)
        else:
            input_score = 1.0
        outputs = [item.concept for item in tool.outputs if item.required]
        if available_outputs and outputs:
            matched = sum(
                1
                for concept in outputs
                if any(self.ontology.check_link(concept, None, target, None).valid for target in available_outputs)
            )
            output_score = matched / len(outputs)
        else:
            output_score = 1.0
        trust = float(trust_state.get("score", 0.5))
        rating = tool.rating_value if tool.rating_value is not None else 0.5
        rating = max(0.0, min(1.0, float(rating)))
        return round(input_score * 0.45 + output_score * 0.25 + trust * 0.2 + rating * 0.1, 6)

    def _available_concepts(
        self, subgoal: SubGoal, subgoals: list[SubGoal]
    ) -> list[str]:
        concepts: list[str] = []
        for key in subgoal.slots:
            if key == "question":
                capability = subgoal.capability
                concepts.append(
                    "DocumentQuestion"
                    if capability == "AnswerFromDocument"
                    else "NaturalLanguageQuery"
                )
            elif key in SLOT_CONCEPTS:
                concepts.append(SLOT_CONCEPTS[key])
        subgoal_map = {item.id: item for item in subgoals}
        for dep_id in subgoal.depends_on:
            dependency = subgoal_map.get(dep_id)
            if dependency is None:
                continue
            capability = self.ontology.capabilities.get(dependency.capability, {})
            concepts.extend(capability.get("outputs", []))
        return list(dict.fromkeys(concepts))

    def _ontology_filter_reason(
        self, tool: ToolSpec, subgoal: SubGoal, available: list[str]
    ) -> str | None:
        for item in tool.inputs:
            if not item.required:
                continue
            if item.name in subgoal.slots:
                continue
            if any(
                self.ontology.check_link(concept, None, item.concept, None).valid
                for concept in available
            ):
                continue
            return (
                f"input {item.name} ({item.concept}) cannot be supplied by the task "
                f"or upstream outputs"
            )
        return None

    def _build_bindings(
        self,
        tool: ToolSpec,
        subgoal: SubGoal,
        dependency_steps: list[PlanStep],
    ) -> tuple[dict[str, str], list[str]]:
        bindings: dict[str, str] = {}
        errors: list[str] = []
        for item in tool.inputs:
            if item.name in subgoal.slots:
                bindings[item.name] = f"$task.{item.name}"
                continue
            found = False
            for step in dependency_steps:
                source_tool = self.graph.get(step.tool_id)
                if source_tool is None:
                    continue
                for output in source_tool.outputs:
                    if output.name == item.name:
                        bindings[item.name] = f"${step.id}.{output.name}"
                        found = True
                        break
                    if item.name in output.fields:
                        bindings[item.name] = (
                            f"${step.id}.{output.name}.{item.name}"
                        )
                        found = True
                        break
                    if self.ontology.check_link(
                        output.concept, output.unit, item.concept, item.unit
                    ).valid:
                        bindings[item.name] = f"${step.id}.{output.name}"
                        found = True
                        break
                if found:
                    break
            if not found and item.required:
                errors.append(
                    f"required input {item.name} ({item.concept}) has no value source"
                )
        return bindings, errors

    def _link_checks(
        self,
        target_tool: ToolSpec,
        subgoal: SubGoal,
        dependency_steps: list[PlanStep],
    ) -> list[LinkCheck]:
        checks: list[LinkCheck] = []
        for step in dependency_steps:
            source_tool = self.graph.get(step.tool_id)
            if source_tool is None:
                continue
            for target_input in target_tool.inputs:
                if not target_input.required:
                    continue
                if target_input.name in subgoal.slots:
                    continue
                options = []
                for output in source_tool.outputs:
                    result = self.ontology.check_link(
                        output.concept,
                        output.unit,
                        target_input.concept,
                        target_input.unit,
                    )
                    options.append((output, result))
                valid = [item for item in options if item[1].valid]
                if valid:
                    output, result = sorted(
                        valid,
                        key=lambda item: (
                            item[1].conversion_required,
                            item[0].concept,
                        ),
                    )[0]
                elif options:
                    output, result = options[0]
                else:
                    output = None
                    result = None
                if output is None or result is None:
                    checks.append(
                        LinkCheck(
                            source_step=step.id,
                            target_step=subgoal.id,
                            source_concept="none",
                            target_concept=target_input.concept,
                            valid=False,
                            reason=f"No output source for {target_input.name}.",
                        )
                    )
                    continue
                checks.append(
                    LinkCheck(
                        source_step=step.id,
                        target_step=subgoal.id,
                        source_concept=output.concept,
                        target_concept=target_input.concept,
                        source_unit=output.unit,
                        target_unit=target_input.unit,
                        concept_ok=result.concept_ok,
                        units_ok=result.units_ok,
                        valid=result.valid,
                        reason=result.reason,
                    )
                )
        return checks

    def _resolve_bindings(
        self,
        bindings: dict[str, str],
        subgoal: SubGoal,
        outputs: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        resolved: dict[str, Any] = {}
        for name, reference in bindings.items():
            if reference.startswith("$task."):
                key = reference[len("$task.") :]
                if key not in subgoal.slots:
                    raise ValueError(f"task slot {key} is missing")
                resolved[name] = subgoal.slots[key]
                continue
            if not reference.startswith("$"):
                resolved[name] = reference
                continue
            path = reference[1:].split(".")
            step_id = path[0]
            value: Any = outputs.get(step_id)
            if value is None:
                raise ValueError(f"output of step {step_id} is unavailable")
            for key in path[1:]:
                if not isinstance(value, dict) or key not in value:
                    raise ValueError(f"upstream value {reference} is unavailable")
                value = value[key]
            resolved[name] = value
        return resolved

    @staticmethod
    def _topological_order(subgoals: list[SubGoal]) -> list[SubGoal]:
        remaining = {item.id: item for item in subgoals}
        ordered: list[SubGoal] = []
        while remaining:
            progressed = False
            for item in list(remaining.values()):
                if all(dep not in remaining for dep in item.depends_on):
                    ordered.append(item)
                    remaining.pop(item.id)
                    progressed = True
                    break
            if not progressed:
                ordered.extend(remaining.values())
                break
        return ordered

    def _synthesize_answer(
        self,
        plan: ExecutionPlan,
        status: TaskStatus,
        failures: list[str],
    ) -> str:
        parts: list[str] = []
        substituted = any(step.substituted_from for step in plan.steps)
        for step in plan.steps:
            if step.status not in {StepStatus.completed, StepStatus.substituted}:
                continue
            output = step.output or {}
            capability = step.capability
            if capability == "GetWeatherForecast" and "forecast" in output:
                forecast = output["forecast"]
                location = forecast.get("location") or "the requested location"
                parts.append(
                    f"Weather for {location} on {forecast.get('date', 'the requested date')}: "
                    f"high {forecast.get('temp_max')} {forecast.get('unit', 'C')}, "
                    f"low {forecast.get('temp_min')} {forecast.get('unit', 'C')}, "
                    f"{forecast.get('precipitation_probability', 'n/a')}% chance of precipitation."
                )
            elif capability == "ConvertCurrency" and "conversion" in output:
                conversion = output["conversion"]
                rate = float(conversion.get("rate") or 0.0)
                converted = float(conversion.get("amount") or 0.0)
                source_amount = (converted / rate) if rate else converted
                parts.append(
                    f"{source_amount:,.2f} {conversion.get('from')} is approximately "
                    f"{converted:,.2f} {conversion.get('currency')} "
                    f"at rate {conversion.get('rate')} ({conversion.get('date')})."
                )
            elif capability == "GetCountryFacts" and "country" in output:
                country = output["country"]
                population = country.get("population", 0)
                parts.append(
                    f"{country.get('name')}: capital {country.get('capital')}, "
                    f"population {population:,}, region {country.get('region')}."
                )
            elif capability == "GetPublicHolidays" and "holidays" in output:
                holidays = output["holidays"]
                preview = "; ".join(
                    f"{item.get('date')} {item.get('name')}" for item in holidays[:5]
                )
                parts.append(
                    f"{len(holidays)} public holidays found. {preview}."
                )
            elif capability == "SearchResearchPapers" and "papers" in output:
                papers = output["papers"]
                preview = "; ".join(
                    f"{item.get('title')} ({item.get('url')})" for item in papers[:3]
                )
                parts.append(f"Top research results: {preview}.")
            elif capability == "QueryStructuredData" and "table" in output:
                table = output["table"]
                rows = table.get("rows") or []
                if len(rows) == 1 and len(rows[0]) == 1:
                    key, value = next(iter(rows[0].items()))
                    parts.append(f"The database returned {key} = {value}.")
                else:
                    preview = "; ".join(
                        ", ".join(f"{key}={value}" for key, value in row.items())
                        for row in rows[:5]
                    )
                    parts.append(
                        f"The read-only SQL query returned {table.get('row_count', len(rows))} "
                        f"row(s): {preview}."
                    )
                parts.append(f"Executed SQL: {table.get('sql', '')}")
            elif capability == "AnswerFromDocument" and "answer" in output:
                payload = output["answer"]
                citations = payload.get("citations") or []
                citation = citations[0].get("name") if citations else "the uploaded document"
                parts.append(f"{payload.get('answer')} (Source: {citation}.)")
            elif capability == "SearchNews" and "articles" in output:
                articles = output["articles"]
                preview = "; ".join(
                    f"{item.get('title')} ({item.get('source')})" for item in articles[:3]
                )
                parts.append(f"Latest news: {preview}.")
            elif capability == "GetCryptoPrice" and "price" in output:
                price = output["price"]
                parts.append(
                    f"1 {price.get('asset')} is currently {float(price.get('price') or 0):,.2f} "
                    f"{price.get('currency')} with a market cap of "
                    f"{float(price.get('market_cap') or 0):,.0f} {price.get('currency')} "
                    f"(updated {price.get('last_updated')})."
                )
            elif capability == "SearchTVShows" and "shows" in output:
                shows = output["shows"]
                preview = "; ".join(
                    f"{item.get('name')} ({item.get('premiered') or 'n/a'}, "
                    f"rating {item.get('rating') or 'n/a'})"
                    for item in shows[:3]
                )
                parts.append(f"TV shows found: {preview}.")
            elif capability == "SearchBooks" and "books" in output:
                books = output["books"]
                preview = "; ".join(
                    f"{item.get('title')} by {item.get('author') or 'unknown author'} "
                    f"({item.get('first_publish_year') or 'n/a'})"
                    for item in books[:3]
                )
                parts.append(f"Books found: {preview}.")
            elif capability == "TranslateText" and "translation" in output:
                translation = output["translation"]
                parts.append(
                    f"Translation ({translation.get('source_language')} to "
                    f"{translation.get('target_language')}): {translation.get('text')}."
                )
            elif capability == "GetCurrentTime" and "time" in output:
                current = output["time"]
                parts.append(
                    f"Current time in {current.get('timezone')}: {current.get('datetime')} "
                    f"(UTC offset {current.get('utc_offset')})."
                )
            elif capability == "GetSunTimes" and "sun" in output:
                sun = output["sun"]
                seconds = int(sun.get("day_length") or 0)
                day_length = f"{seconds // 3600}h {(seconds % 3600) // 60}m"
                parts.append(
                    f"Sunrise {sun.get('sunrise')}, sunset {sun.get('sunset')}, "
                    f"solar noon {sun.get('solar_noon')}, day length {day_length}."
                )
            elif capability == "SearchRecipes" and "meals" in output:
                meals = output["meals"]
                preview = "; ".join(
                    f"{item.get('name')} ({item.get('category')}, {item.get('area')})"
                    for item in meals[:3]
                )
                ingredients = (meals[0].get("ingredients") or []) if meals else []
                parts.append(
                    f"Recipes found: {preview}. Main recipe ingredients: "
                    f"{', '.join(str(item) for item in ingredients[:6])}."
                )
            elif capability == "GetSportsScores" and "scores" in output:
                scores = output["scores"]
                preview = "; ".join(
                    f"{item.get('away_team')} {item.get('away_score')} - "
                    f"{item.get('home_score')} {item.get('home_team')} "
                    f"({item.get('status')})"
                    for item in scores[:3]
                )
                parts.append(f"Latest scores: {preview}.")
        if substituted:
            parts.append(
                "A provider failed during execution, so the Client recovered the chain "
                "with a type-compatible substitute behind the circuit breaker."
            )
        if status != TaskStatus.completed:
            if failures:
                parts.append("Some steps failed: " + "; ".join(failures))
            else:
                parts.append("The task did not complete successfully.")
        if not parts:
            parts.append("No step produced an answer.")
        return " ".join(parts)

    def _mode(self, plan: ExecutionPlan | None = None) -> str:
        if self.settings.offline_mode:
            return "offline"
        if plan is not None:
            sources = {
                step.source for step in plan.steps if step.source and step.status != StepStatus.skipped
            }
            if "fixture" in sources:
                return "live-with-fixture-fallback"
        return "live"

    def _trace(
        self,
        task_id: str,
        event_type: str,
        actor: str,
        summary: str,
        data: dict[str, Any] | None = None,
    ) -> TraceEvent:
        return self.traces.add_event(task_id, event_type, actor, summary, data)

    async def _publish(self, message: BaseMessage, task_id: str) -> None:
        await self.bus.publish(message, task_id=task_id)

    @staticmethod
    def _dedupe(values: Sequence[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
