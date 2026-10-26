# Architecture

## System boundary

This repository implements the merged Agent Bazaar system: the Client and Provider agents, trust registry, circuit breaker, web interface/trace viewer, the knowledge layer and Mapper, and the Auditor and monitoring layer, with explicit adapters between them. It is a complete runnable system with deterministic fallbacks, not a mock UI over empty interfaces.

```text
Browser
  |
  +-- GET  /                      Jinja2 shell
  +-- GET  /static/*              CSS and vanilla JS
  +-- POST /api/tasks             JSON task request
  |
FastAPI (app/main.py)
  |
  +-- AppServices (app/services.py)
        |
        +-- ClientAgent (app/agents/client.py)
        |     +-- TaskPlanner
        |     +-- GraphRAGRetriever
        |     +-- Ontology
        |     +-- AuditorBridge
        |     +-- TrustRegistry
        |     +-- CircuitBreakerRegistry
        |     +-- ProviderRegistry
        |     +-- TraceStore / MessageBus
        |
        +-- Auditor (src/agent_bazaar_auditor)
        |     +-- claim verification and evidence judging
        |     +-- safe probes and payload validation
        |     +-- rule + embedding drift detection
        |     +-- trust ledger and feed
        |
        +-- SQLite
        |     +-- cache.db
        |     +-- traces.db
        |     +-- trust.db
        |     +-- documents.db
        |     +-- sample_university.db
        |
        +-- Evaluations (app/evaluation)
```

## Components

| Component | Responsibility | Main file |
|---|---|---|
| Client agent | Orchestrates one task from decomposition to answer | `app/agents/client.py` |
| Planner | Deterministic decomposition with optional LLM fallback | `app/agents/planner.py` |
| Ontology | Concepts, capabilities, units, subtype and link checks | `app/knowledge/ontology.py` |
| Tool graph | Tool catalogue, graph neighbors, RDF export | `app/knowledge/graph.py` |
| GraphRAG | TF-IDF retrieval with graph-neighbor expansion | `app/knowledge/retrieval.py` |
| Providers | Live/fixture execution, schema validation, cache | `app/providers/` |
| Provider registry | Tool-to-provider lookup, mirrors, failure controls | `app/providers/registry.py` |
| Auditor adapter | Claim labels, drift alerts, contradiction signals, Auditor API | `app/agents/auditor_bridge.py` |
| Mapper adapter | Listing ingestion and ontology-checked corrections | `app/agents/mapper_stub.py` |
| Trust registry | Beta score, history, replay, demotion | `app/core/trust_registry.py` |
| Circuit breaker | Per Client-to-Provider link state machine | `app/core/circuit_breaker.py` |
| Trace store | Durable events, task results and messages | `app/core/tracing.py` |
| Interface | Task workbench, trace, monitoring, library, documents | `app/web/` |

## Client loop

1. **Decompose.** `TaskPlanner.decompose` detects weather, currency, holiday, country, research, SQL and document intents. Weather and SQL/document questions are handled robustly; an optional LLM planner is used only when the deterministic planner finds nothing.
2. **Retrieve.** For each sub-goal, `GraphRAGRetriever.search` filters the catalogue to the required capability, ranks by TF-IDF cosine similarity, normalizes scores, and expands the top seeds through graph neighbors.
3. **Filter.** The Client rejects unknown capabilities and candidates that cannot satisfy required input concepts.
4. **Verify.** The Auditor returns per-claim labels (`Verified`, `Supported`, `Unsupported` or `Contradicted`). Catalogue tools are checked by the real Auditor; local SQL, document and adversarial providers use the seeded fallback.
5. **Rank.** The policy partitions candidates by pricing tier (`free`, `freemium`, `paid`, `unknown`), then ranks inside the tier:

   ```text
   base = relevance x trust x quality x rating_factor
   quality = doc_quality^w1 x mapping_coverage^w2 x chain_fit^w3
   score = base; if contradicted: score *= contradicted_penalty
   if demoted or breaker open: score = 0 and candidate becomes ineligible
   ```

   Paid and keyed tools remain visible with a reason but are not executable. Candidates are sorted by tier, eligibility and score. Claim labels and trust history are shown in the UI.
6. **Compose.** The planner selects one eligible tool per sub-goal. For dependent sub-goals, `app/agents/client.py` builds input bindings from earlier outputs. Each dependency link is checked with `Ontology.check_link`.
7. **Validate links.** Concept compatibility and unit compatibility are checked before a provider is called. Unit mismatches are rejected; convertible units are flagged, and the synthetic conversion step is applied where the Client supports it.
8. **Execute.** Steps run in topological order. Provider responses are schema-validated against the tool's output concept fields. Successful outputs feed downstream bindings.
9. **Recover.** On failure, if substitution is enabled, the Client asks the graph for a compatible tool with the same capability, compatible inputs and compatible output concepts. The substitute runs behind the same breaker link. If no substitute is available, the branch fails and the Client reports a partial/failed result.
10. **Learn.** Execution, schema and claim outcomes update the trust registry. The Client publishes a `TrustUpdate` message, records breaker transitions and writes trace events.
11. **Answer.** The Client synthesizes an answer from successful branches, includes provider citations where relevant, and records warnings such as fixture use.

## Trust model

The score is a Beta-style estimate with a neutral prior:

```text
score = (successes + 1) / (successes + failures + 2)
```

Signals:

| Signal | Default weight | Meaning |
|---|---:|---|
| `probe` | 1.0 | Auditor live probe |
| `call` | 1.0 | Client execution outcome |
| `schema` | 0.5 | Response schema validity |
| `rating` | 0.75 (or supplied) | Developer rating |
| `contradiction` | 2.0 | Claim contradicted by evidence |

A provider is demoted when it has at least `trust_min_evidence` weighted evidence and its score is below `trust_demotion_threshold` (default 0.40). Demoted providers receive score zero and are ineligible until their score recovers. `trust_history` records every update, and `replay` recomputes the score from history so the UI can show that persisted state and derived state agree.

## Auditor integration

`AuditorBridge` implements the Client's Auditor contract on top of
`src/agent_bazaar_auditor`. Six application tools map to Auditor catalogue ids
(`open-meteo-forecast` -> `open-meteo`, `frankfurter-currency` -> `frankfurter`,
`nominatim-geocode` -> `nominatim`, `restcountries-facts` -> `rest-countries`,
`nager-holidays` -> `nager-date`, `arxiv-search` -> `arxiv`). Verification runs
in a worker thread because the Auditor is synchronous and owns mutable
baselines; the bridge serialises calls with one lock. The three local-only
providers keep the seeded fallback from `AuditorStub`.

The interface exposes the Auditor through `GET /api/auditor`,
`GET /api/auditor/trust`, `POST /api/auditor/verify/{tool}` and
`POST /api/auditor/monitor/{tool}`. The demo drift route uses the Auditor's
own mock provider and rename drift detector when the tool is in the catalogue;
for local-only tools it falls back to the documented injected alert. Drift
alerts are converted into the application `DriftAlertMessage`, recorded as a
contradiction in the trust registry, and surfaced by `/api/monitoring`.

## Circuit breaker

Each Client-to-Provider link has an independent breaker:

- **closed**: calls allowed.
- **open**: calls blocked after `breaker_failure_threshold` consecutive failures, or immediately after drift/manual trip.
- **half-open**: after `breaker_cooldown_seconds`, exactly one trial call is allowed.
  - success -> closed and failure count reset.
  - failure -> open again with a new cooldown.

Breakers are process-local by design. Trust, traces and messages are persisted in SQLite.

## Provider behavior

`BaseProvider.call` order:

1. injected demo failure, if scheduled;
2. cache lookup;
3. offline fixture, if offline mode is forced;
4. live API call;
5. fixture fallback if the live call fails;
6. schema validation and a structured error if all paths fail.

Providers never silently return malformed data: schema errors are attached to the response and the Client records them.

Mirrors exist for weather, geocoding, currency, holidays, country facts and arXiv. The adversarial mock weather provider reports Fahrenheit output and is used to show why unit-aware composition matters.

## Interface

The web UI is intentionally dependency-free vanilla JS. It talks only to documented HTTP endpoints. The shell has four page routes: the workflow dashboard, the service marketplace, the self-healing monitor and the interface library. It renders:

- the answer and its evidence warnings, with result cards for terminal chain steps;
- ranked candidates with relevance, trust, claim badges, breaker state and reasons;
- chain steps with link checks, bindings, latency, provider source and raw output;
- the trace timeline with grouped, expandable event data;
- trust and breaker tables, drift alerts, the Auditor mode and catalogue coverage;
- marketplace cards and a tool modal with pricing tier, access requirement,
  price, rating, documentation quality, mapping coverage and the reason a tool
  is not executable;
- corrections, uploads and document questions.

The marketplace supports a "Free first" sort that follows the ranking policy's
tier order (`free`, `freemium`, `paid`, `unknown`) and then trust. `frontend-preview/`
is a standalone, mock-data design snapshot; the served interface is `app/web/`.

## Persistence

| Store | Contents |
|---|---|
| `cache.db` | Provider response cache keyed by provider and normalized params |
| `traces.db` | Trace events, task results and agent messages |
| `trust.db` | Current trust state and append-only trust history |
| `documents.db` | Uploaded document metadata and extracted passages |
| `sample_university.db` | Seeded read-only demo database |
| `knowledge_graph.ttl` | RDF export of the local tool/ontology graph |

`data/` and `reports/*.json` are runtime/generated artifacts. The sample repository includes the generated evaluation reports, but runtime databases are intentionally ignored.

## Failure and safety properties

- No provider is called with unresolved required inputs.
- No link is accepted if its source concept is incompatible with the target concept.
- No link is accepted if units have different dimensions.
- A contradicted tool is penalized; optionally it is excluded.
- An open breaker removes the primary candidate from selection.
- A failed primary call can recover through a compatible substitute.
- Every decision and provider outcome is traceable by task ID.
- External APIs are free and keyless; no secret is required to run the project.
