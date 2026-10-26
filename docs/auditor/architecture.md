# Architecture

The Auditor is a standalone service and library that answers three questions:

1. Is a tool's documentation true, false, or unverifiable under current evidence?
2. Has the tool's observable response contract drifted?
3. What trust signal should the registry receive as a result?

It is built as a pipeline of small, injectable components. The default composition is offline and deterministic; live probes, HTTP trust delivery, and LLM judging are optional.

## Component map

| Area | Module | Responsibility |
| --- | --- | --- |
| Catalog | `tools.py` | 15 tool specifications, documentation corpus, 47 claims. |
| Claim model | `claims.py` | Claim/Evidence types, extraction, retrieval, heuristic and LLM judges. |
| Decision | `decision.py` | Fixed document-stance × probe-outcome decision table. |
| Probes | `probes/definitions.py` | URLs, expected fields, types, units, ranges, safe inputs. |
| Probe harness | `probes/harness.py` | Fixture/live selection, cache, HTTP execution, throttling. |
| Payload validation | `probes/models.py` | Nested-path resolution and schema/type/unit/range checks. |
| Drift | `drift/` | Baseline persistence, rule checks, schema embeddings, combined detector. |
| Mocks | `mocks/` | Controllable providers for every evaluated failure mode. |
| Orchestration | `auditor.py` | Probe once, judge evidence, label claims, emit trust and alerts. |
| Contracts | `messages.py` | Verify, drift, trust, feedback, correction, and repair messages. |
| Trust | `trust.py` | Beta-style ledger, feed, optional HTTP registry delivery. |
| Scheduling | `scheduler.py` | Due-tool selection and adaptive re-probe intervals. |
| Persistence | `store.py`, `drift/baseline.py` | JSON/JSONL artifacts, baselines, ledgers, reports. |
| API | `api.py` | Read endpoints plus verify, monitor, probe, and mock control. |
| CLI | `cli.py` | Catalog, extract, verify, probe, monitor, evaluate, demo, serve. |
| Evaluation | `evaluation/` | Metrics, claim/drift/trust experiments, combined report. |

## Verification flow

```text
VerifyRequest(tool_id, claims?)
        │
        ▼
Select catalog claims (or caller-supplied claims)
        │
        ▼
Probe once if any requested claim is probeable
        │
        ├── fixture or live response
        ├── store probe artifact
        ├── validate expected fields/types/units/ranges
        ├── compare response schema with baseline
        └── send probe outcome to trust feed
        │
        ▼
For each claim:
        ├── retrieve supporting/contradicting documentation
        ├── judge documentation stance
        ├── evaluate probe evidence for the claim
        ├── combine through the decision table
        ├── record assessment and evidence
        └── send contradiction trust update when applicable
        │
        ▼
VerifyResult with assessments, coverage, probe metadata, notes, and alerts
```

A single probe serves every claim for a tool. This is important for rate limits and latency, and it means a claim is never evaluated against a different response than the schema checks saw.

## Why one probe per verification

The Auditor is not a per-claim API caller. It probes the documented endpoint once, validates the response as a whole, and then evaluates each claim against fields in that response. If a probe cannot run, the result records that fact and the decision table produces `Supported` or `Unsupported` rather than pretending the claim was verified.

This design also makes drift coherent: the same payload that is judged for claims is compared with the baseline. A rename can therefore produce both a claim-level contradiction and a field-level drift alert without a second request.

## Claim extraction

`HeuristicClaimExtractor` converts documentation lines into claims with:

- `id`, `tool_id`, `text`;
- `claim_type`: `output_field`, `unit`, `range`, `limit`, `auth_required`, `safe_input`, `behavior`, `other`;
- optional `field_path`, `expected_value`, `expected_unit`, `expected_type`;
- `probeable`, `source`, `confidence`, and tags.

The catalog ships curated claims for eval stability. `extract_claims` can still run the extractor over the same documentation; extraction is exposed through `agent-bazaar-auditor extract`.

An LLM extractor is available behind the same `ClaimExtractor` protocol. It is not used by default because deterministic extraction keeps evaluation reproducible and avoids an external dependency.

## Evidence retrieval and judging

`DocumentRetriever` indexes documentation chunks with hashing embeddings and cosine similarity. `HeuristicEvidenceJudge` determines whether retrieved chunks support, contradict, or are silent on a claim. It understands field names, expected types, units, numeric limits, and authentication language.

Retrieval is not a formality: the judge receives the claim and the retrieved chunks, and the final decision includes documentation stance. A probe result alone cannot label a claim `Verified` when the documentation does not assert it; the cap is `Supported`.

`LLMEvidenceJudge` and `CachedLLM` are optional. The LLM client uses an OpenAI-compatible chat-completions endpoint, JSON mode when requested, and a deterministic response cache. The reported evaluation stays on the deterministic path.

## Decision policy

The table in `decision.py` is intentionally small and auditable:

| Document stance | Probe outcome | Label |
| --- | --- | --- |
| Contradicts | Any | Contradicted |
| Supports | Agrees | Verified |
| Supports | Disagrees | Contradicted |
| Supports | Unknown, not probeable, or probe error | Supported |
| Silent | Agrees | Supported |
| Silent | Disagrees | Contradicted |
| Silent | Unknown, not probeable, or probe error | Unsupported |

The key policy choice is that missing evidence is not negative evidence. An outage does not turn a supported claim into a contradiction. Conversely, a documented field that is absent from a successful response is a contradiction.

## Probe harness

`ProbeHarness` has two modes:

- **Fixture mode** (default): loads deterministic responses from `probes/definitions.py` or mock overrides.
- **Live mode**: sends a GET request to the probe URL with a fixed safe input.

Live mode includes:

- a clear `User-Agent`;
- timeout configuration via `ABA_REQUEST_TIMEOUT`;
- per-host throttling;
- a file-backed cache with a TTL;
- safe JSON/XML parsing;
- status-code and transport-error capture rather than exceptions escaping the pipeline.

The harness never sends destructive requests and does not accept arbitrary caller-supplied URLs. Probe definitions are code-reviewed.

## Payload validation

`validate_payload` resolves dotted paths, including paths that traverse lists, and checks:

- required field presence;
- expected Python/JSON types;
- units and numeric ranges;
- observed limits where a probe can safely exercise them.

Validation issues are retained even when the tool returns HTTP 200. This is what allows the Auditor to distinguish "the endpoint works" from "the response still matches the contract".

## Drift detection

Drift is evaluated at the response-schema level, not just at the claim level.

### Baseline

`BaselineStore` persists one `BaselineRecord` per tool/embedder/dimension combination. A record contains:

- normalized schema text;
- embedding vector;
- embedder name and dimension count;
- creation timestamp and last probe round.

Baselines are created on the first verification unless `establish_baseline=False`.

### Rules

`drift/rules.py` compares the current payload with the probe definition's field contract:

- removed field;
- renamed field with a candidate replacement;
- changed type;
- changed unit;
- out-of-range values;
- unexpected new required parameters;
- transport failure.

Rules are high-precision and explainable. They can also be precise to a fault: a garbage-200 response that preserves the mapped fields still passes field and type checks.

### Embedding detector

`drift/embedding.py` builds a compact textual schema summary and embeds it with `HashingEmbedder`. Cosine distance above a tuned threshold raises an embedding alert. This catches structural pollution that rules miss.

### Combined detector

`DriftMonitor` evaluates rules and embeddings according to `mode` (`full`, `rule_only`, `embedding_only`) and merges overlapping findings. Each `DriftCheck` carries mode, distance, threshold, rule results, and alerts. `Auditor` emits a `TrustUpdate(outcome=drift)` for each alert and attaches the alerts to `VerifyResult`.

The threshold is not hard-coded into the detector. The evaluation tunes it from known-good variations and passes it in; production can continue collecting variations and re-tune.

## Trust loop

`TrustFeed` receives `TrustUpdate` messages and:

1. appends them to `trust_updates.jsonl`;
2. updates the local `TrustLedger`;
3. forwards them to an optional `TrustRegistry` implementation.

The local ledger uses a Beta-style score:

```text
score = (successes + 1) / (successes + failures + 2)
```

The Auditor emits at least these outcomes:

- `probe_pass` and `probe_fail` for whole-response checks;
- `schema_invalid` when validation fails;
- `drift` for detector alerts;
- `contradiction` for contradicted claims.

The trust registry is an interface, not a hard dependency. `HttpTrustRegistry` is a minimal adapter; a production registry can implement `push` directly.

## Scheduling

`ProbeScheduler` stores per-tool entries with next-probe time, last outcome, unstable flag, and failure count. Clean tools use `ABA_SCHEDULER_BASE_INTERVAL`; unstable tools use the shorter `ABA_SCHEDULER_UNSTABLE_INTERVAL`. `apply_feedback` moves a tool into or out of the unstable set based on probe/drift outcomes. The scheduler persists its state and can call a supplied probe callback for every due tool.

## Persistence

When `persist=True`, `ArtifactStore` writes under `ABA_OUTPUT_DIR`:

```text
outputs/
├── baselines.json
├── trust_ledger.json
├── messages.jsonl
├── probe_index.jsonl
├── knowledge.jsonl
├── graph_writes.jsonl
├── drift_alerts.jsonl
├── trust_updates.jsonl
├── probes/<tool>/<timestamp>.json
├── verifications/<tool>/<timestamp>.json
└── reports/
```

Artifacts use stable IDs and include correlation IDs so a verification can be reconstructed from its request, probe, validation, assessments, evidence, alerts, and trust updates. The demo uses a temporary directory and no persistence, so repeated runs do not contaminate the evaluation.

## API boundary

The HTTP API is intentionally thin. It validates request shape, calls the same `Auditor` methods as the CLI, and serializes message dictionaries. It is a local development and integration surface, not a hardened multi-tenant service:

- default bind address is `127.0.0.1`;
- CORS is permissive for local front-end experiments;
- there is no authentication;
- mock control is disabled unless `--mock` is passed.

Do not expose `serve --mock` to an untrusted network.

## Extension points

| Need | Implement | Injection point |
| --- | --- | --- |
| Better claim extraction | `ClaimExtractor` | `Auditor(extractor=...)` |
| Stronger evidence judge | `EvidenceJudge` | `Auditor(judge=...)` |
| Semantic embeddings | `EmbeddingModel` | `Auditor(embedder=...)` |
| Real trust registry | `TrustRegistry` | `TrustFeed(registry=...)` |
| Persistent trust backend | Replace `TrustLedger` | Wrap `TrustFeed` |
| More probes | Add `ProbeDefinition` | `build_probe_definitions()` |
| New drift rule | Add rule check | `DriftMonitor.check` |
| New artifact sink | Replace `ArtifactStore` | `Auditor(store=...)` |

The evaluation must remain deterministic with the default implementations. If a component with network or nondeterministic behavior is injected, pin or cache it before using the scores in a report.

## Failure behavior

- **Unknown tool:** `KeyError` surfaces to the CLI/API as a 400 or exit code 2.
- **No probe definition:** claims are still assessed; probe outcome is `not_probeable`.
- **Probe transport error:** recorded with status/error; claims do not get `Verified`.
- **Malformed JSON:** recorded as an error; no baseline update.
- **Empty or missing payload:** schema validation fails; drift rules may also fire.
- **Persist disabled:** all in-memory behavior is unchanged; only artifact writes are skipped.

## Boundaries

This repository owns the audit and trust-signal layer. It does not:

- re-map fields after a rename (Mapper);
- decide whether to substitute a provider (Client);
- provide a production passive-trust ranking (trust registry);
- authenticate end users or API callers;
- guarantee real-world accuracy from a curated dataset.

Those boundaries are reflected in the message contracts and in the evaluation's stated limitations.
