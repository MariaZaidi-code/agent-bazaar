# Work-Plan Mapping

This document maps the **Auditor and Monitoring Lead** work plan (10 weeks, Proposal v1.3) to what is implemented in this repository. It distinguishes working standalone code, interface-ready integration points, and work that still needs the other team members or a longer data-collection period.

## Ownership coverage

| Work-plan responsibility | Status | Where |
| --- | --- | --- |
| Auditor agent with VerifyRequest/VerifyResult | Implemented | `auditor.py`, `messages.py`, `cli.py`, `api.py` |
| Claim extraction and evidence retrieval | Implemented with deterministic defaults; LLM adapters available | `claims.py`, `retrieval.py`, `llm.py` |
| Four-label verdicts with stored evidence | Implemented | `decision.py`, `auditor.py`, `store.py` |
| Live probing for 12–15 keyless APIs | Implemented for 15 APIs; offline fixtures by default | `probes/`, `tools.py` |
| Rule-based drift detection | Implemented | `drift/rules.py` |
| Embedding-based drift detection | Implemented with a deterministic hashing embedder | `drift/embedding.py`, `embeddings.py` |
| DriftAlert flow | Implemented | `messages.py`, `drift/`, `store.py` |
| Mock providers and control interface | Implemented for all listed behaviours | `mocks/provider.py`, `mocks/registry.py` |
| Scheduler with shorter unstable intervals | Implemented, including manual trigger | `scheduler.py` |
| TrustUpdate feed | Implemented with local ledger and optional HTTP registry | `trust.py` |
| Seeded claim dataset and evaluations | Implemented: 60 claims, 20 drift scenarios, trust experiment | `data/`, `evaluation/` |
| Documentation of messages, probes and mock controls | Implemented | `README.md`, `docs/`, `probes/definitions.py` |
| Closed loop with Mapper, Client and registry | Contract-ready only | Out of this repository |
| Independent blind labelling and Cohen's kappa | Not done | Shared team duty |
| Re-mapping accuracy | Not scored here | Mapper dependency |

## Requirements

| Requirement | How it is covered |
| --- | --- |
| FR4: claim verification | Four labels, evidence retrieval, probe checks, fixed decision table. |
| FR6 monitoring side | Re-probing, drift rules, schema embeddings, DriftAlert. |
| FR7: drift detection | Rule and embedding detectors with tuned threshold and ablation. |
| FR8 monitoring side | TrustUpdate outcomes and adaptive re-probe scheduling. |
| FR11: probe/debuggability | Probe definitions, artifacts, correlation ids, HTTP API, CLI. |
| NFR3: honest coverage | Coverage reported per tool and overall; offline fixture caveat included. |
| NFR4: explainable labels | Rationale, quoted documentation, probe checks, fixed decision table. |
| NFR5: independent agent state | Auditor state, baselines, trust ledger, and scheduler persist separately. |

## Deliverables

### 1. Auditor agent

`Auditor.verify` accepts a tool and optional claims, performs one shared probe, assesses every claim, and returns `VerifyResult`. `handle_verify_request` accepts the serialized request contract. The CLI and HTTP API both call the same code path.

Status: **implemented**.

### 2. Claim-verification pipeline

The pipeline contains all six planned stages:

1. claim extraction with type, field path, expected type/unit/range, and source text;
2. document retrieval with hashing embeddings and cosine similarity;
3. probe selection based on claim type and probe definition;
4. live or fixture probing with deterministic checks;
5. label decision through the fixed table;
6. persistence of claim, evidence, label, correlation id, and trust updates.

The production plan calls for Maria's document ingestion and vector index. This repository uses its own deterministic retriever so it can run alone. `ClaimExtractor`, `EvidenceJudge`, and `EmbeddingModel` are protocols, so those components can be injected without changing the pipeline.

Status: **implemented standalone; integration adapters needed**.

### 3. Probe harness

Fifteen keyless APIs are defined: Frankfurter, Open-Meteo, Nominatim, REST Countries, Nager.Date, arXiv, CoinGecko, Cat Fact, Dog CEO, IPify, JokeAPI, WorldTimeAPI, DataMuse, Open Library, and USGS Earthquake.

Each definition includes endpoint, safe input, expected fields, types, units, optional ranges, and claim checks. The harness supports fixtures, live HTTP, caching, file-backed throttling, timeouts, error capture, XML and JSON parsing.

Status: **implemented**. Evaluate uses offline fixtures so results are reproducible and do not depend on provider availability.

### 4. Drift detection

Rule checks cover missing/renamed fields, type changes, unit changes, out-of-range values, new required parameters, and transport failures. The embedding check compares a structural summary with a stored baseline using cosine distance. Alerts contain tool id, field path, detector, old description, new sample, severity, distance, round, and details.

Threshold tuning is implemented in `evaluation/drift_eval.py`: it measures known-good variation distances, sets the threshold above the maximum plus a margin, then reports detection and false alarms. The shipped threshold is 0.252.

Status: **implemented on controlled known-good variations**. The plan's "several days of real baseline probes" still needs a longer collection window before a production threshold can be frozen.

### 5. Mock providers

Behaviours: normal, rename field, unit change, type change, remove field, garbage 200, exaggerated claim, outage, flapping, and dishonest. Every provider has realistic documentation and a deterministic fixture. `MockRegistry.control` changes behaviour at run time. The mock state is logged as ground truth for evaluation, and `/mock` exposes the same control when `serve --mock` is used.

Status: **implemented**. The Provider interface should still be aligned with Rameen's production interface if the team standard differs.

### 6. Scheduler

`ProbeScheduler` tracks next probe time, last outcome, failure count, and unstable status. Clean tools use the base interval; tools with alerts, contradictions, or failures use the unstable interval. `trigger` and `trigger_all` support demonstrations and tests. `apply_feedback` responds to outcomes.

Status: **implemented standalone**. The long-running daemon is not part of the CLI; callers invoke due tools through `run_due`.

### 7. Evaluation reports

- 60 claims: 32 real Verified, 8 real Supported, 10 seeded Contradicted, 10 seeded Unsupported.
- 20 injected drift scenarios across eight behaviours.
- Rule-only versus full ablation with a garbage-200 focus.
- 30 known-good variations for false alarms.
- Trust experiment with 5 honest and 5 bad providers.
- Claim latency and token-use reporting; offline token use is zero.

Status: **implemented**. See [the Auditor evaluation](evaluation.md) and `outputs/reports/`.

### 8. Documentation

Message schemas, probe definitions, mock control, CLI, API, architecture, evaluation, and setup are documented. The mock control interface is documented in [the protocol](protocol.md) and `mocks/registry.py`.

Status: **implemented**.

## Week-by-week plan

| Week | Planned output | Repository evidence |
| ---: | --- | --- |
| 1 | Message drafts, API shortlist | `messages.py`, `tools.py`, [the protocol](protocol.md) |
| 2 | Probe-eligible list, false-claim design started | 15 definitions, `data/seeded_claims.json` |
| 3 | First probe definitions, baseline collection started | Full probe definitions; baseline store; synthetic known-good variations |
| 4 | Extraction prompt v1, full probe list | `LLMClaimExtractor` prompt, 15 definitions |
| 5 | Mock framework v1 | All mock behaviours and registry |
| 6 | Verification pipeline without live probing | `Auditor`, decision table, fixture mode |
| 7 | Working Auditor, claim results | `VerifyResult`, claim evaluation |
| 8 | Drift results, scheduler, TrustUpdate | `drift/`, `scheduler.py`, `trust.py`, drift evaluation |
| 9 | Remaining mocks, trust and ablation results | Full mock set, rule-only/full comparison, trust experiment |
| 10 | Report sections, cached data for demo | `docs/`, frozen fixtures, `agent-bazaar-auditor demo` |

This table shows where each planned output now lives. It does not imply that the calendar schedule was followed.

## Interfaces and dependencies

### Received from Maria

| Dependency | Status in this repository |
| --- | --- |
| Documentation chunks | Standalone documentation corpus in `tools.py`; ingestion adapter not included. |
| Vector index with fixed embedding | Standalone hashing index in `retrieval.py`; production index can be injected. |
| Validated Claim/Evidence graph write | JSONL writes in `store.py`; production write adapter not included. |
| Mapper handles DriftAlert | Alert contract is ready; Mapper implementation is external. |

### Received from Rameen

| Dependency | Status in this repository |
| --- | --- |
| Provider interface for mocks | Compatible callable provider shape; confirm exact production interface. |
| Trust registry endpoint | `TrustRegistry` protocol and `HttpTrustRegistry` adapter. |
| Circuit breaker on DriftAlert | Alerts are emitted; circuit breaker is external. |

### Given to the team

| Output | Status |
| --- | --- |
| DriftAlert and Claim/Evidence schemas | `messages.py`, [the protocol](protocol.md) |
| Mock provider framework | `mocks/` |
| Working VerifyRequest/VerifyResult | `auditor.py`, API, CLI |
| Ground-truth logs for injected changes | Evaluation JSON and scenario dataset |
| Frozen claim/drift sets for B1 and B2 | `data/` |

## Definition of Done

| Criterion | Status |
| --- | --- |
| All four labels with stored evidence for loaded tools | Done |
| Re-evaluate on re-probe | Done |
| 12–15 probe APIs with published coverage | 15 APIs; 76.67% overall, 100% of probeable claims |
| Rule and embedding drift implemented | Done |
| Threshold tuned and justified | Tuned on 30 known-good variations; longer real baseline still recommended |
| Closed loop alert → re-map → trust drop → circuit breaker → substitution | Contracts ready; integration with Maria and Rameen still required |
| Mock providers cover all behaviours and log ground truth | Done |
| Claim and drift results with datasets and methods | Done |
| Report sections and cached demo data | Docs and deterministic fixtures done; final team report still external |
| Independent blind labelling with Cohen's kappa | Not done; shared team duty |
| Re-mapping accuracy | Not scored; Mapper dependency |
| Ablations: no Auditor, no drift, rule-only | Rule-only/full implemented; no-Auditor/no-drift baseline scoring is external |
| Cost: latency and tokens per claim/probe | Latency and offline token use reported; live token cost not measured |

## Honest gaps and next integration tasks

1. **Production knowledge layer.** Replace the standalone retriever and JSONL writes with Maria's fixed embedding index and validated graph-write function. Keep the decision table unchanged.
2. **Blind labels and kappa.** Have two team members label a shared subset without seeing the Auditor's output, then report agreement. The current 60-claim set was curated during development, so the perfect score is a regression result, not an unbiased accuracy estimate.
3. **Real baseline window.** Collect real known-good responses over several days. Recompute the threshold and false-alarm rate before production.
4. **Closed loop.** Have the Mapper consume `DriftAlert.details.candidate_path`, the registry consume `TrustUpdate`, and the Client apply circuit-breaker/substitution policy. Measure the hand-off latency and any message-schema changes.
5. **Re-mapping accuracy.** Score the Mapper's proposed field mappings against injected ground truth. This is a Mapper metric, not an Auditor metric.
6. **B1/B2 scoring.** Hand the frozen sets to Rameen and score the same items. The repository supplies the data but does not implement either baseline.
7. **Live cost report.** Run a small live subset with the LLM judge enabled to measure prompt/completion tokens and p95 latency against provider rate limits.
8. **Provider interface sign-off.** Confirm that the mock callable shape matches Rameen's Provider interface before integration.
