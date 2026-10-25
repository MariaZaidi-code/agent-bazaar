from __future__ import annotations

import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from .claims import (
    Claim,
    ClaimExtractor,
    DocumentJudgement,
    Evidence,
    EvidenceJudge,
    HeuristicClaimExtractor,
    HeuristicEvidenceJudge,
)
from .config import Settings
from .decision import decide_label, explain_label
from .drift import BaselineStore, DriftCheck, DriftMonitor
from .embeddings import EmbeddingModel, HashingEmbedder
from .enums import ClaimLabel, DocStance, ProbeOutcome, ProbeSource, TrustOutcome
from .messages import (
    ClaimAssessment,
    CoverageReport,
    TrustUpdate,
    VerifyRequest,
    VerifyResult,
)
from .probes.definitions import ProbeDefinition, build_probe_definitions
from .probes.harness import ProbeHarness
from .probes.models import ClaimProbeCheck, PayloadValidation, ProbeResult, evaluate_claim, validate_payload
from .retrieval import DocumentRetriever
from .store import ArtifactStore
from .tools import ToolSpec, build_catalog
from .trust import HttpTrustRegistry, TrustFeed, TrustLedger
from .utils import percentage, stable_id, truncate, utc_now


@dataclass
class ClaimCoverage:
    assessed: list[ClaimAssessment] = field(default_factory=list)
    probeable: int = 0
    probed: int = 0


def aggregate_coverage(results: Iterable[VerifyResult]) -> CoverageReport:
    results = list(results)
    total = sum(result.coverage.total_claims for result in results)
    probeable = sum(result.coverage.probeable_claims for result in results)
    probed = sum(result.coverage.probed_claims for result in results)
    per_tool = {result.tool_id: result.coverage.coverage_percent for result in results}
    sources: dict[str, int] = {}
    notes: list[str] = []
    for result in results:
        for source, count in result.coverage.probe_sources.items():
            sources[source] = sources.get(source, 0) + count
        notes.extend(result.coverage.notes)
    return CoverageReport(
        total_claims=total,
        probeable_claims=probeable,
        probed_claims=probed,
        coverage_percent=percentage(probed, total),
        probeable_coverage_percent=percentage(probed, probeable),
        per_tool=per_tool,
        probe_sources=sources,
        notes=sorted(set(notes)),
    )


class Auditor:
    def __init__(
        self,
        catalog: dict[str, ToolSpec] | None = None,
        harness: ProbeHarness | None = None,
        extractor: ClaimExtractor | None = None,
        judge: EvidenceJudge | None = None,
        retriever: DocumentRetriever | None = None,
        embedder: EmbeddingModel | None = None,
        settings: Settings | None = None,
        store: ArtifactStore | None = None,
        monitor: DriftMonitor | None = None,
        trust_feed: TrustFeed | None = None,
        persist: bool = True,
    ) -> None:
        self.settings = (settings or Settings.from_env()).prepare()
        self.catalog = catalog or build_catalog()
        self.harness = harness or ProbeHarness(
            definitions=build_probe_definitions(),
            live=self.settings.live,
            cache_dir=self.settings.cache_dir / "probes",
        )
        self.definitions = self.harness.definitions
        self.embedder = embedder or HashingEmbedder(self.settings.embedding_dimensions)
        self.extractor = extractor or HeuristicClaimExtractor()
        self.judge = judge or HeuristicEvidenceJudge()
        self.retriever = retriever or DocumentRetriever(self.embedder)
        self.persist = persist
        self.store = store or (ArtifactStore(self.settings.outputs_dir) if persist else None)
        self.monitor = monitor or DriftMonitor(
            BaselineStore(self.settings.outputs_dir / "baselines.json", persist=persist),
            embedder=self.embedder,
            threshold=self.settings.drift_threshold,
            mode=self.settings.drift_mode,
        )
        registry = HttpTrustRegistry(self.settings.trust_registry_url) if self.settings.trust_registry_url else None
        self.trust_ledger = TrustLedger(self.settings.outputs_dir / "trust_ledger.json" if persist else None)
        self.trust_feed = trust_feed or TrustFeed(
            log_path=self.settings.outputs_dir / "trust_updates.jsonl" if persist else None,
            registry=registry,
            ledger=self.trust_ledger,
        )

    def get_tool(self, tool_id: str) -> ToolSpec:
        try:
            return self.catalog[tool_id]
        except KeyError as error:
            raise KeyError(f"Unknown tool {tool_id}") from error

    def get_definition(self, tool_id: str) -> ProbeDefinition:
        try:
            return self.definitions[tool_id]
        except KeyError as error:
            raise KeyError(f"No probe definition for tool {tool_id}") from error

    def claims_for(self, tool_id: str) -> list[Claim]:
        tool = self.get_tool(tool_id)
        if tool.claims:
            return list(tool.claims)
        return self.extractor.extract(tool_id, tool.documentation)

    def extract_claims(self, tool_id: str) -> list[Claim]:
        tool = self.get_tool(tool_id)
        return self.extractor.extract(tool_id, tool.documentation)

    def probe(self, tool_id: str, force_live: bool = False, force_fixture: bool = False) -> ProbeResult:
        result = self.harness.probe(tool_id, force_live=force_live and not force_fixture)
        if result.source is ProbeSource.FIXTURE:
            result.metadata["offline_fixture"] = True
        return result

    def _probe_evidence(self, claim: Claim, probe: ProbeResult, check: ClaimProbeCheck, artifact: str) -> Evidence:
        return Evidence(
            id=stable_id(claim.id, "probe", probe.timestamp),
            claim_id=claim.id,
            kind="probe",
            source=f"{claim.tool_id}:probe:{probe.timestamp}",
            summary=check.reason,
            quote="; ".join(check.checks),
            probe_outcome=check.outcome.value,
            metadata={
                "status_code": probe.status_code,
                "latency_ms": probe.latency_ms,
                "timestamp": probe.timestamp,
                "source": probe.source.value,
                "artifact": artifact,
                "url": probe.url,
                "raw_response": truncate(probe.payload, 800),
                "error": probe.error,
            },
        )

    def _document_evidence(
        self,
        claim: Claim,
        judgement: DocumentJudgement,
        documentation: list[str],
        retriever: DocumentRetriever,
    ) -> Evidence | None:
        if judgement.evidence is not None:
            judgement.evidence.metadata.setdefault("documentation_chunks", len(documentation))
            return judgement.evidence
        if not judgement.quote:
            return None
        retrieved = retriever.retrieve_scored(claim.text, documentation, top_k=1)
        source = f"{claim.tool_id}:documentation"
        metadata = {"documentation_chunks": len(documentation)}
        if retrieved:
            metadata["retrieved_chunk"] = retrieved[0].chunk_id
            metadata["retrieval_score"] = round(retrieved[0].score, 6)
        return Evidence(
            id=stable_id(claim.id, "document"),
            claim_id=claim.id,
            kind="document",
            source=source,
            summary=f"Documentation {judgement.stance.value}",
            quote=judgement.quote,
            doc_stance=judgement.stance,
            metadata=metadata,
        )

    def assess_claim(
        self,
        claim: Claim,
        probe: ProbeResult | None = None,
        validation: PayloadValidation | None = None,
        documentation: list[str] | None = None,
        probe_artifact: str = "",
        judge_chunks: list[str] | None = None,
    ) -> ClaimAssessment:
        tool = self.get_tool(claim.tool_id)
        definition = self.definitions.get(claim.tool_id)
        chunks = documentation if documentation is not None else tool.documentation
        retrieved = judge_chunks if judge_chunks is not None else self.retriever.retrieve(claim.text, chunks)
        judgement = self.judge.judge(claim, retrieved)
        evidence: list[Evidence] = []
        document_evidence = self._document_evidence(claim, judgement, chunks, self.retriever)
        if document_evidence is not None:
            evidence.append(document_evidence)
        check = ClaimProbeCheck(ProbeOutcome.NOT_PROBEABLE, "Claim is not probeable by a live call.")
        probed = False
        probe_error = ""
        if probe is not None and definition is not None and claim.probeable and definition.probeable:
            probed = True
            check = evaluate_claim(claim, probe, definition)
            probe_error = check.reason if check.outcome is ProbeOutcome.PROBE_ERROR else ""
            evidence.append(self._probe_evidence(claim, probe, check, probe_artifact))
        label = decide_label(judgement.stance, check.outcome)
        rationale = explain_label(judgement.stance, check.outcome, label)
        if check.reason and judgement.stance in {DocStance.SUPPORTS, DocStance.SILENT}:
            rationale = f"{rationale} Probe detail: {check.reason}"
        if validation is not None and not validation.ok and probe is not None and probe.ok:
            rationale = f"{rationale} Payload validation issues: {len(validation.issues)}."
        return ClaimAssessment(
            claim=claim,
            label=label,
            doc_stance=judgement.stance,
            probe_outcome=check.outcome,
            evidence=evidence,
            rationale=rationale,
            probe_source=probe.source.value if probe is not None else "",
            probed=probed,
            probe_error=probe_error,
            probe_status_code=probe.status_code if probe is not None else None,
            probe_latency_ms=probe.latency_ms if probe is not None else None,
            probe_artifact=probe_artifact,
            probe_checks=list(check.checks),
        )

    def _coverage(
        self,
        tool_id: str,
        assessments: list[ClaimAssessment],
        probe: ProbeResult | None,
        notes: list[str],
    ) -> CoverageReport:
        total = len(assessments)
        probeable = sum(1 for item in assessments if item.probed or (item.claim.probeable and item.probe_outcome is not ProbeOutcome.NOT_PROBEABLE))
        probed = sum(1 for item in assessments if item.probed)
        sources: dict[str, int] = {}
        if probe is not None and probed:
            sources[probe.source.value] = probed
        if probe is not None and probe.source is ProbeSource.FIXTURE:
            notes.append("Probe source is an offline fixture; these are not live-probe results.")
        if probe is not None and probe.source is ProbeSource.CACHE:
            notes.append("Probe source is a cached live response.")
        if probe is not None and not probe.ok:
            notes.append(f"Probe failed for {tool_id}: {probe.error or probe.status_code}.")
        return CoverageReport(
            total_claims=total,
            probeable_claims=probeable,
            probed_claims=probed,
            coverage_percent=percentage(probed, total),
            probeable_coverage_percent=percentage(probed, probeable),
            per_tool={tool_id: percentage(probed, total)},
            probe_sources=sources,
            notes=sorted(set(notes)),
        )

    def _send_probe_trust(
        self,
        tool_id: str,
        probe: ProbeResult,
        validation: PayloadValidation | None,
        correlation_id: str,
    ) -> None:
        sender = "auditor"
        if validation is not None:
            outcome = TrustOutcome.SCHEMA_VALID if validation.ok else TrustOutcome.SCHEMA_INVALID
            self._send_trust(
                TrustUpdate(
                    sender=sender,
                    correlation_id=correlation_id,
                    tool_id=tool_id,
                    outcome=outcome,
                    reason="Probe payload schema validation.",
                    value=1.0 if validation.ok else 0.0,
                )
            )
        outcome = TrustOutcome.PROBE_PASS if probe.ok else TrustOutcome.PROBE_FAIL
        self._send_trust(
            TrustUpdate(
                sender=sender,
                correlation_id=correlation_id,
                tool_id=tool_id,
                outcome=outcome,
                reason=probe.error or f"Probe returned HTTP {probe.status_code}.",
                value=1.0 if probe.ok else 0.0,
            )
        )

    def _send_trust(self, update: TrustUpdate) -> None:
        self.trust_feed.send(update)
        if self.store is not None:
            self.store.record_trust(update)

    def verify(
        self,
        tool_id: str,
        claims: list[Claim] | None = None,
        correlation_id: str = "",
        reprobe_round: int = 0,
        force_live: bool = False,
        request_id: str = "",
        establish_baseline: bool = True,
        documentation: list[str] | None = None,
    ) -> VerifyResult:
        self.get_tool(tool_id)
        request_claims = list(claims) if claims is not None else self.claims_for(tool_id)
        correlation_id = correlation_id or stable_id("verify", tool_id, utc_now())
        request = VerifyRequest(
            sender="client",
            correlation_id=correlation_id,
            tool_id=tool_id,
            claims=claims,
            request_all_claims=claims is None,
            reprobe_round=reprobe_round,
        )
        if request_id:
            request.id = request_id
        if self.store is not None:
            self.store.record_message(request)
        started_at = utc_now()
        started = time.perf_counter()
        notes: list[str] = []
        probe: ProbeResult | None = None
        validation: PayloadValidation | None = None
        artifact = ""
        drift_check: DriftCheck | None = None
        definition = self.definitions.get(tool_id)
        should_probe = definition is not None and definition.probeable and any(claim.probeable for claim in request_claims)
        if should_probe:
            probe = self.probe(tool_id, force_live=force_live)
            if self.store is not None:
                artifact = self.store.record_probe(probe, correlation_id)
            validation = validate_payload(definition, probe.payload) if probe.payload is not None else None
            drift_check = self.monitor.check(
                tool_id,
                probe,
                definition,
                probe_round=reprobe_round,
                correlation_id=correlation_id,
                establish_if_missing=establish_baseline,
            )
            if self.store is not None:
                self.store.record_drift(drift_check, correlation_id)
            for alert in drift_check.alerts:
                self._send_trust(
                    TrustUpdate(
                        sender="auditor",
                        correlation_id=correlation_id,
                        tool_id=tool_id,
                        outcome=TrustOutcome.DRIFT,
                        reason=f"{alert.detector.value} drift: {alert.field_path}",
                        claim_id="",
                        value=alert.distance,
                    )
                )
            self._send_probe_trust(tool_id, probe, validation, correlation_id)
        else:
            notes.append("No probe-eligible claim was requested for this tool.")
        assessments: list[ClaimAssessment] = []
        for claim in request_claims:
            if claim.tool_id != tool_id:
                raise ValueError(f"Claim {claim.id} belongs to {claim.tool_id}, not {tool_id}")
            assessment = self.assess_claim(
                claim,
                probe=probe,
                validation=validation,
                documentation=documentation,
                probe_artifact=artifact,
            )
            assessments.append(assessment)
            if self.store is not None:
                self.store.record_assessment(assessment, tool_id, correlation_id)
                self.store.record_claim_evidence(claim, assessment.evidence, assessment.label, correlation_id)
            if assessment.label is ClaimLabel.CONTRADICTED:
                self._send_trust(
                    TrustUpdate(
                        sender="auditor",
                        correlation_id=correlation_id,
                        tool_id=tool_id,
                        outcome=TrustOutcome.CONTRADICTION,
                        reason=assessment.rationale,
                        claim_id=claim.id,
                        value=0.0,
                    )
                )
        duration_ms = (time.perf_counter() - started) * 1000.0
        covered = [item for item in assessments if item.probed]
        if probe is not None:
            notes.append(
                f"Probe source={probe.source.value}; status={probe.status_code}; latency_ms={probe.latency_ms:.2f}; artifact={artifact or 'not stored'}."
            )
        if drift_check is not None:
            notes.append(f"Drift check mode={drift_check.mode}; alerts={len(drift_check.alerts)}.")
        result = VerifyResult(
            sender="auditor",
            correlation_id=correlation_id,
            request_id=request.id,
            tool_id=tool_id,
            assessments=assessments,
            coverage=self._coverage(tool_id, assessments, probe, notes),
            started_at=started_at,
            finished_at=utc_now(),
            duration_ms=round(duration_ms, 3),
            probe_source=probe.source.value if probe is not None else "",
            notes=notes,
            probe_artifact=artifact,
            probe_status_code=probe.status_code if probe is not None else None,
            probe_latency_ms=probe.latency_ms if probe is not None else None,
            probe_valid=validation.ok if validation is not None else None,
            drift_alerts=drift_check.alerts if drift_check is not None else [],
        )
        if self.store is not None:
            self.store.record_message(result)
            stored = self.store.record_verification(result)
            result.notes.append(f"Verification artifact={stored}; assessed={len(covered)}/{len(assessments)}.")
        return result

    def handle_verify_request(self, request: VerifyRequest) -> VerifyResult:
        claims = None if request.request_all_claims else request.claims
        result = self.verify(
            request.tool_id,
            claims=claims,
            correlation_id=request.correlation_id or request.id,
            reprobe_round=request.reprobe_round,
            request_id=request.id,
            documentation=None,
        )
        return result

    def verify_all(self, tool_ids: list[str] | None = None, force_live: bool = False) -> dict[str, VerifyResult]:
        targets = tool_ids or list(self.catalog)
        return {tool_id: self.verify(tool_id, force_live=force_live) for tool_id in targets}

    def monitor_tool(
        self,
        tool_id: str,
        probe_round: int = 1,
        force_live: bool = False,
        establish_baseline: bool = False,
    ) -> VerifyResult:
        return self.verify(
            tool_id,
            reprobe_round=probe_round,
            force_live=force_live,
            establish_baseline=establish_baseline,
        )

    def trust_snapshot(self) -> list[dict[str, Any]]:
        return self.trust_ledger.leaderboard()
