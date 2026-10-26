# Agent Bazaar

A marketplace where agents map, find, verify, chain and learn to trust third-party services.

Ontology- and knowledge-graph-driven multi-agent system, BS Artificial Intelligence,
University of Central Punjab.

Agent Bazaar is a multi-agent marketplace that finds, verifies, composes, executes and
repairs third-party tool chains. A developer asks for a task in natural language; the Client
agent retrieves candidate tools with GraphRAG, filters them through a shared ontology, checks
claim labels, ranks by trust, validates type and unit links, executes through Provider agents,
and substitutes a compatible backup if a provider fails.

This repository holds three merged stacks:

- the **knowledge layer** (`src/agent_bazaar`): upper ontology and units, RDF knowledge graph,
  vector index, ingestion utility, Mapper agent and mapping evaluation helpers;
- the **Auditor and monitoring layer** (`src/agent_bazaar_auditor`): claim extraction, evidence
  judging, safe probing, rule and embedding drift detection, mock providers, trust updates and
  its own reproducible evaluation;
- the **Client, Provider and Interface application** (`app`): FastAPI service, provider agents,
  trust registry, circuit breakers, trace viewer, evaluation suites and the browser interface.

All three run without API keys: the application uses free, keyless public APIs or
deterministic offline fixtures, the knowledge layer runs offline against the committed
seed corpus, and the Auditor runs against frozen fixtures and datasets.

## Documentation

Knowledge layer and Mapper:

- [Week 1 scope and shared protocol](docs/week1-scope-and-protocol.md)
- [Ontology, units and SHACL](docs/ontology.md)
- [Graph schema and queries](docs/graph-schema.md)
- [Mapper protocol](docs/mapper-protocol.md)
- [API sourcing, quality profiling and free-first reasoning](docs/api-sourcing-and-reasoning.md)
- [Onboarding guide](docs/onboarding.md)
- [Decisions and known limitations](docs/decisions.md)
- [Evaluation plan](docs/evaluation-plan.md)
- [Specification corpus provenance](data/specs/README.md)

Client, Provider and Interface:

- [Architecture and formulas](docs/architecture.md)
- [Agent message protocol](docs/message-protocol.md)
- [Evaluation methodology and results](docs/evaluation.md)
- [Demonstration script](docs/demo-guide.md)
- [Mapper/Auditor integration contracts](docs/integration.md)
- [Requirement-to-code traceability](docs/requirements-traceability.md)

Auditor and monitoring:

- [Auditor overview](docs/auditor/overview.md)
- [Auditor architecture](docs/auditor/architecture.md)
- [Auditor protocol and message contracts](docs/auditor/protocol.md)
- [Auditor evaluation](docs/auditor/evaluation.md)
- [Auditor demo guide](docs/auditor/demo-guide.md)
- [Auditor work-plan mapping](docs/auditor/work-plan-mapping.md)

## Team branches

- `maria` - knowledge layer and Mapper lead (ontology, knowledge graph, vector index, ingestion utility, Mapper agent, mapping evaluation)
- `qaim` - Auditor and monitoring lead
- `rameen` - Client, Provider and interface lead

## What is included

### Client, Provider and Interface

- **Client agent** with decomposition, GraphRAG retrieval, ontology filtering, claim-aware ranking, dependency-aware composition, type/unit link checks, execution, recovery and answer synthesis.
- **Free-first ranking** with a deterministic tier partition (free, freemium, paid, unknown), weighted quality factors, a shrunk rating factor and an executability gate: paid and keyed tools are ranked and shown with a reason but never called.
- **Provider layer** for Open-Meteo, Frankfurter, OpenStreetMap Nominatim, REST Countries, Nager.Date, arXiv, a read-only university SQLite database and uploaded-document question answering.
- **Resilience** with backup mirrors for six live providers, an adversarial Fahrenheit weather mock, trust-weighted ranking, a three-state circuit breaker and circuit-breaker substitution.
- **Trust registry** with Beta-style scoring, signal history, contradiction penalties, demotion and replay verification.
- **Trace viewer** persisting every decision, provider call, verification result and recovery event in SQLite.
- **Responsive web interface** for running chains, inspecting candidates, viewing traces, monitoring trust and breakers, staging corrections, uploading documents and injecting demo failures.
- **Evaluation suite** with 50 matching tasks, 15 chain tasks, B1/B2 baseline comparison, 7 substitution cases, 6 trust scenarios, a seven-configuration ablation and a 48-task free-first ranking suite.
- **52 automated tests**, Ruff checks and GitHub Actions CI.
- **43 integration tests** for the bridge between the application and the knowledge layer.

### Auditor and Monitoring

- **Claim verification** over 15 keyless APIs and 47 curated claims, with the fixed four-label decision table and evidence from both documentation and probes.
- **Safe probing** with fixtures, rate limiting, caching and JSON/XML payload validation.
- **Drift monitoring** that combines rule checks with schema embeddings and emits field-level `DriftAlert` messages.
- **Trust updates** through a Beta-style ledger and an optional HTTP registry feed.
- **Mock providers** for rename, removal, type change, unit change, garbage `200`, outage, flapping and dishonest responses.
- **Reproducible evaluation** with 60 labelled claims, 20 injected drift scenarios, false-alarm controls and a dishonest-provider trust experiment.
- **Application integration** through `AuditorBridge`: the six catalogue tools used by the app are verified by the real Auditor, the local SQL/document/mock providers keep the seeded fallback, and `/api/auditor/*` exposes catalog, verify, monitor and trust data.
- **32 Auditor tests** in addition to the application and knowledge-layer suites.

### Knowledge layer and Mapper

- **Ontology** with a frozen 12-class upper ontology, a curated domain layer of 60 concepts, unit families with compatibility rules, and SHACL shapes for validation.
- **RDF knowledge graph** store with loaders and query helpers for tools, concepts, units, capabilities and mappings.
- **API sourcing** with a pluggable source protocol, the APIs.guru directory and a local upload source, a manifest v2 that carries the commercial and access facts of every document, a refresh diff, and a curated override file that wins over the extraction rules.
- **Quality profiles** with one `ab:Offering` node per tool: pricing tier, access requirement, price, rate limit, probe budget, licence, terms URL, documentation quality, mapping coverage, rating and the evidence behind each fact.
- **Vector index** for ontology terms, tool descriptions and corrections, with a deterministic hashing embedder for offline runs.
- **Ingestion utility** for OpenAPI, PDF, DOCX and plain-text specifications.
- **Mapper agent** with retrieval, LLM mapping, SHACL repair, bounded staging of corrections and drift detection.
- **Pipeline** that takes a service listing through ingestion, mapping and a validated graph write.
- **Mapping evaluation** helpers for metrics, ablations and learning curves.
- **130 unit and end-to-end tests**.

## Quickstart (PowerShell)

All three stacks install from the same dependency set, so a single virtual environment serves
all three quickstarts.

### Knowledge layer and Mapper

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# Deterministic, offline path
python scripts/build_ontology.py --offline
python scripts/seed_graph.py --offline --hash-embeddings
python scripts/demo_mapper.py
python -m pytest
```

`python -m pytest` runs the whole merged suite: the 130 knowledge-layer tests, the 50
application tests, the 43 integration tests, the 32 Auditor tests and the 6 Auditor bridge
tests, 261 in total.

This uses the committed 8-spec seed corpus and the deterministic hashing
embedder. No API key is needed. To fetch the full corpus and use the embedding
model:

```powershell
python -m pip install -e ".[dev,embeddings]"
python scripts/fetch_specs.py --limit 100
python scripts/build_ontology.py --offline

# Optional: onboard the full corpus instead of the 8 seed specs (slower; overwrites graph.ttl)
python scripts/seed_graph.py --offline --specs data\specs
```

For LLM ontology generation or LLM mapping, copy the example settings and export a
key in the current shell:

```powershell
Copy-Item config\settings.example.yaml config\settings.yaml
$env:GROQ_API_KEY = "..."     # example config default; Gemini/OpenRouter also supported
```

`config/settings.yaml` is gitignored. Secrets are read from environment variables;
nothing secret is written to the repository. The code does not load a `.env` file
automatically.

### Client, Provider and Interface

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

Open <http://127.0.0.1:8000>.

If PowerShell blocks activation, no activation is needed; use the explicit `.venv\Scripts\python.exe` commands above.
`scripts/setup.ps1` performs the environment creation, dependency install and test run, and
`scripts/run.ps1` starts the server.

### Auditor and Monitoring

```powershell
python -m agent_bazaar_auditor catalog
python -m agent_bazaar_auditor verify open-meteo
python -m agent_bazaar_auditor monitor open-meteo --rounds 2
python -m agent_bazaar_auditor demo
python -m agent_bazaar_auditor evaluate
```

The same package is installed as the `agent-bazaar-auditor` command by
`python -m pip install -e ".[dev]"`. The Auditor defaults to frozen fixtures and writes
generated probes, baselines and reports under `outputs/` (gitignored). Add `--live` to
`verify`, `probe` or `monitor` to contact the keyless provider explicitly; the evaluation
never uses the network.

The application runs the same Auditor in fixture mode by default. Set `AB_AUDITOR_LIVE=true`
to let `/api/auditor/verify` and `/api/auditor/monitor` probe live when requested, and
`AB_AUDITOR_PERSIST=false` to disable the Auditor artifact store. See
[docs/auditor/overview.md](docs/auditor/overview.md) for the complete command and API
reference.

### VS Code

1. Open the `agent-bazaar` folder.
2. Run **Python: Select Interpreter** and choose `.venv\Scripts\python.exe`.
3. Open a terminal and run `.\.venv\Scripts\python.exe run.py`.
4. Open port `8000` or browse to <http://127.0.0.1:8000>.

### Configuration

All settings are optional. The application reads them from the environment or from a
local `.env` file:

```dotenv
AB_OFFLINE_MODE=true
AB_RUNTIME_DIR=data/runtime
AB_LLM_PROVIDER=none
AB_AUDITOR_LIVE=false
AB_AUDITOR_PERSIST=true
```

`AB_OFFLINE_MODE=true` is recommended for the first run and for evaluation. Live mode contacts only free, keyless public APIs. Set `AB_OFFLINE_MODE=false` to use them. If a live provider fails, the app falls back to an offline fixture and records the failure.

The optional LLM planner supports OpenAI-compatible providers (`none`, `openrouter`, `groq`, `gemini`). The complete demonstration and evaluation work without an LLM.

The free-first ranking policy has its own settings, all optional:

```dotenv
AB_PRICING_POLICY=prefer_free
AB_TIER_ORDER=["free","freemium","paid","unknown"]
AB_DOC_QUALITY_WEIGHT=0.4
AB_MAPPING_COVERAGE_WEIGHT=0.3
AB_CHAIN_FIT_WEIGHT=0.3
AB_MIN_RATING_COUNT=3
AB_RATING_FLOOR=0.5
AB_REQUIRE_KNOWN_LICENCE=false
```

`AB_PRICING_POLICY=prefer_free` keeps the commercial tier as a partition, so a free tool is always ranked above a paid one. `AB_REQUIRE_KNOWN_LICENCE=true` additionally refuses to execute a tool whose licence is unknown. See [the sourcing and reasoning document](docs/api-sourcing-and-reasoning.md) for what the policy does with these values.

## Five-minute demonstration

1. Run the first example: **Weather + currency**.
2. Inspect the ranked candidates, claim badges, selected tools and the weather/currency chain.
3. Open **Agent trace** and expand an event to see its stored inputs and outputs.
4. Open **Self-healing monitor**, click **Fail next weather call**, then run the weather example again.
5. The primary weather provider fails, the breaker records the failure, the backup mirror executes, and the trace shows `substitution_succeeded`.
6. Click **Simulate drift**, then run the task again. The backup is selected up front because the primary link is open.
7. Open the document icon in the top bar, upload a TXT/MD/CSV/PDF/DOCX file, and ask a grounded question through the Client.
8. Open **Service marketplace**, open the adversarial mock, and stage an ontology correction from its tool modal.

## Architecture

```text
Developer UI
   |
   v
 ClientAgent
   |-- TaskPlanner --------------- deterministic or optional LLM decomposition
   |-- GraphRAGRetriever --------- TF-IDF plus ontology-graph expansion
   |-- Ontology ------------------ concepts, capabilities, units, link checks
   |-- AuditorBridge ------------- real Auditor for catalogue tools, seeded fallback
   |-- TrustRegistry ------------- Beta score, history, demotion
   |-- CircuitBreakerRegistry ---- closed / open / half-open
   |-- ProviderRegistry ---------- live providers, mirrors, fixtures
   |
   v
 SQLite: traces, trust, cache, documents, university database

Knowledge layer (src/agent_bazaar)
   listing -> ingestion -> Mapper -> validated RDF graph write
   ontology (upper classes, 60 domain concepts, units, SHACL shapes)
   graph (tools, concepts, units, capabilities, mappings)
   vector index (ontology terms, tool descriptions, corrections)
   |
   v
  app/integration: shared vocabulary, ontology bridge, graph adapter, mapper adapter,
                   runtime wiring of the knowledge layer

Auditor layer (src/agent_bazaar_auditor)
   documentation -> claim extraction -> evidence judge
   keyless API -> safe probe -> payload validation
   baseline -> rule + embedding drift -> DriftAlert / TrustUpdate
   |
   v
  app/agents/auditor_bridge.py: catalogue verification, drift alerts, trust feed,
                                fixture fallback for local-only providers
```

The execution flow is:

1. Decompose the task into typed sub-goals.
2. Retrieve a candidate list for each capability.
3. Filter candidates through the ontology.
4. Attach claim labels from the Auditor adapter; catalogue tools are checked by the real
   Auditor and local-only providers use the seeded fallback.
5. Rank free-first: the commercial tier is a partition (`free`, `freemium`, `paid`,
   `unknown`), and inside a tier the score is
   `relevance x trust x quality x rating factor`, with claim and breaker penalties.
6. Select tools and compute dependency-aware input bindings. Only free and keyless
   tools may be selected.
7. Reject invalid concept or unit links before execution.
8. Execute in topological order.
9. On failure, select a compatible substitute and retry.
10. Record trust updates, breaker transitions, messages and trace events.
11. Synthesize an answer from successful branch outputs.

See [docs/architecture.md](docs/architecture.md) for the component contracts and formulas, and
[docs/graph-schema.md](docs/graph-schema.md) for the knowledge-layer graph schema.

## Repository layout

```text
app/
  agents/        Client, planner, Auditor adapter, Mapper adapter, free-first ranking policy
  baselines/     B1 plain tool-calling and B2 retrieval without graph/ontology
  core/          cache, SQLite, tracing, trust, breakers, LLM, message bus
  data/          ontology, tool catalogue, fixture-backed providers
  evaluation/    datasets, metrics and runnable suites
  integration/   bridge between the knowledge layer and the app (canonical vocabulary and adapters)
  knowledge/     ontology, tool graph, GraphRAG retrieval
  providers/     live/fixture provider agents and mirrors
  web/           FastAPI templates and vanilla JS/CSS interface
  config.py      typed settings with environment overrides
  main.py        FastAPI application and API
  schemas.py     message protocol and domain models
  services.py    composition root
src/agent_bazaar/
  messages/      structured JSON message schemas (protocol)
  ontology/      upper ontology, units, SHACL shapes, domain layer and generator
  kg/            RDF knowledge graph store, loader, query helpers and quality profiles
  vec/           vector index (ontology terms, tool descriptions, corrections)
  ingestion/     OpenAPI, PDF, DOCX and text ingestion utility, listing metadata, spec sources
  mapper/        Mapper agent: retrieval, LLM mapping, SHACL repair, staging, drift
  evaluation/    mapping metrics, ablations and learning-curve helpers
  llm/           cached chat-completions client
  pipeline.py    listing -> ingestion -> mapping -> validated graph write
src/agent_bazaar_auditor/
  claims.py      claim extraction, evidence retrieval and judging
  probes/        definitions, safe HTTP harness, cache and payload checks
  drift/         baselines, rule checks, schema embeddings and combined detector
  mocks/         controllable normal, rename, remove, unit, garbage, outage and flaky providers
  evaluation/    claim, drift and trust experiments with frozen datasets
  auditor.py     end-to-end verification and monitoring flow
  api.py         standalone HTTP API for verify, monitor, probe and trust
  cli.py         catalog, verify, probe, monitor, demo, evaluate and serve commands
scripts/         corpus fetch, ontology build, graph seed, demo and evaluation entry points
                 plus setup.ps1, run.ps1 and evaluate.ps1 for the application
tests/           pytest suite: knowledge layer, application, integration, Auditor and bridge tests
docs/            scope, protocol, ontology, graph, Mapper, onboarding, decisions, evaluation,
                 architecture, message protocol, demo guide, integration, traceability,
                 API sourcing and free-first reasoning, and docs/auditor/ for the Auditor
reports/         generated JSON evaluation reports
outputs/         generated Auditor probes, baselines, ledgers and reports (not committed)
data/
  specs/         generated corpus of 98 specifications; committed 8-spec seed subset, seed manifest,
                 curated live-probe set and README
  overrides/     curated pricing, access and licence overrides that win over the extraction rules
  out/           committed ontology.ttl, graph.ttl, ontology_llm_demo.ttl, domain TTLs and build/seed logs
  eval/          committed 916-row unlabelled mapping template
  vectors/       generated vector index (not committed)
  memory/        generated correction memory (not committed)
  staging/       generated correction staging log (not committed)
  cache/         generated LLM cache (not committed)
  demo/          generated demo workspace from scripts/demo_mapper.py
  runtime/       application runtime state (not committed)
config/          settings.example.yaml; settings.yaml is gitignored
run.py           development entry point
```

Committed artifacts: `data/out/ontology.ttl` (upper ontology, units and 60 concepts),
`data/out/graph.ttl` (8 tools, 467 mapping nodes), `data/out/ontology_llm_demo.ttl` and the
other demo/domain TTLs, `data/out/logs/` build summaries, `data/eval/mapping_gold.jsonl`, the
8-spec seed corpus, `reports/*.json` and the documents under `docs/`.

The Mapper writes validated mappings and uses a bounded repair loop; corrections
are staged before promotion. See the Mapper protocol and decisions documents for
current limitations, including the difference between 512 mapping results and
467 distinct mapping nodes.

## Integration between the knowledge layer and the app

`app/integration/` is the integration surface between the merged stacks, and it is
implemented. The modules are:

| Module | Role |
|---|---|
| `canonical.py` | The single translation point between the two vocabularies. It maps the app's local names (`C`, `F`, `LocationName`, `Coordinates`) onto the canonical knowledge-layer names (`Celsius`, `Fahrenheit`, `PlaceName`, `Position`) and lists the concepts that exist only in the local fallback ontology. |
| `ontology_bridge.py` | The knowledge-layer ontology behind the app ontology API (`exists`, `is_subtype`, `check_capability`, `check_link`, `units_compatible`, `validate_tool`), with the local ontology as the fallback for the concepts the knowledge layer does not model. |
| `graph_adapter.py` | The RDF knowledge graph behind the app tool-graph API (`all`, `get`, `by_capability`, `neighbors`, `compatible_substitutes`, `export_turtle`), with the local catalogue as a fallback for tools that only exist there. |
| `mapper_adapter.py` | The Mapper agent behind the app mapper adapter API (`submit_listing`, `submit_correction`, `staged`, `reset`). Corrections are validated and promoted into the RDF graph instead of only being staged. |
| `messages.py` | Side-effect free conversions between the app schemas and the knowledge-layer message schemas. |
| `runtime.py` | `build_knowledge_layer()` loads the published artifacts `data/out/graph.ttl` and `data/out/ontology.ttl` and wires the knowledge layer into the app. |

The `knowledge_backend` setting selects what the application serves:

| Mode | Ontology | Tool graph | Mapper |
|---|---|---|---|
| `auto` (default) | local fallback ontology | local tool catalogue | knowledge-layer Mapper |
| `rdf` | `KnowledgeOntology` | `RdfToolGraph` | `KnowledgeMapper` |
| `local` | local fallback ontology | local tool catalogue | `MapperStub` |

The default `auto` mode keeps the app ontology and the executable tool catalogue and
uses the real knowledge-layer Mapper for listings and corrections when the published
artifacts are present; without them it falls back to the stub Mapper. `rdf` serves the
whole application from the knowledge layer, and `local` never loads it.

`GET /api/knowledge` reports the RDF layer that is loaded: the graph counts, the number
of concepts, the tools and the paths of the graph and ontology artifacts.

`python -m pytest` runs 261 tests across the knowledge layer, application, integration,
Auditor and bridge suites. All 261 pass on the current checkout. The app-side adapter
boundaries and the method-level contracts are documented in
[docs/integration.md](docs/integration.md).

## Uploaded documents

The document provider accepts `.txt`, `.md`, `.csv`, `.pdf` and `.docx` files up to 10 MB. Text is extracted with `pypdf` or `python-docx`, split into overlapping passages and retrieved with TF-IDF. Answers are extractive and include a source citation. The application seeds a project brief on first run, so document questions work before any upload.

## Evaluation

### Client, Provider and Interface suites

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.run_all
```

Individual suites:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.run_matching
.\.venv\Scripts\python.exe -m app.evaluation.run_chains
.\.venv\Scripts\python.exe -m app.evaluation.run_baselines
.\.venv\Scripts\python.exe -m app.evaluation.run_substitution
.\.venv\Scripts\python.exe -m app.evaluation.run_trust
.\.venv\Scripts\python.exe -m app.evaluation.run_ablations
```

Reports are written to `reports/*.json` and exposed at `/api/evaluations`.

Current offline-fixture run:

| Suite | Cases | Result |
|---|---:|---|
| Matching | 50 tasks / 67 links | MRR 1.000, hit@k 1.000, selected-tool accuracy 1.000 |
| Chains | 15 tasks | Success rate 1.000, trace coverage 1.000 |
| Baselines | 15 tasks plus fault case | Full and B1/B2 both 1.000 on curated chains; fault recovery 1.000 full vs 0.000 baselines |
| Substitution | 7 cases | Recovery accuracy 1.000; negative control correctly did not recover |
| Trust | 6 scenarios | Pass rate 1.000, replay consistency 1.000 |
| Ablations | 7 configurations | Chain success 1.000, recovery 0.714; disabling substitution removes recovery |

These are deterministic offline results. They exercise orchestration, ontology checks, trust, breakers and recovery against controlled fixtures; they are not a claim about live internet reliability. Live mode is the manual integration check for the public APIs. The same figures are reproduced with the knowledge-backed Mapper of the default `auto` backend.

### Free-first ranking suite

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.run_ranking
```

The suite replays 48 hand-checked ranking tasks over the 8 curated capabilities
through the deterministic ranking policy and writes `reports/ranking.json`. It is
not part of `run_all`, so it is run separately.

| Configuration | MRR | NDCG@10 | Free-first rate | Executable-top rate | Tier separation accuracy |
|---|---:|---:|---:|---:|---:|
| `full` | 1.0000 | 1.0000 | 1.0000 | 0.9583 | 1.0000 |
| `no_tier` | 0.6771 | 0.8823 | 0.3542 | 0.3333 | 0.2292 |
| `no_quality` | 0.7049 | 0.9478 | 1.0000 | 0.9375 | 1.0000 |
| `no_rating` | 0.9896 | 0.9984 | 1.0000 | 0.9583 | 1.0000 |

The `no_tier` ablation removes the commercial tier partition, and the free-first
rate falls from 1.0000 to 0.3542: that is the measurable effect of ranking free
tools first. The metric definitions and the threats to validity are in
[the evaluation plan](docs/evaluation-plan.md#11-ranking-evaluation-free-first-ranking).

### Knowledge layer artifacts

```powershell
python scripts\run_eval.py --template
```

| Artifact | Count | Source |
|---|---:|---|
| Specifications fetched | 98 | `data/specs/` corpus |
| Committed seed specifications | 8 | `data/specs/seed/` |
| Tools written | 8 | `data/out/logs/seed_graph.json` |
| Mapping results | 512 | `data/out/logs/seed_graph.json` |
| Distinct graph mapping nodes | 467 | `data/out/graph.ttl` |
| Unmapped fields | 449 | `data/out/logs/seed_graph.json` |
| Frozen domain concepts | 60 | `data/out/ontology.ttl` |
| Mapping evaluation template rows | 916 | `data/eval/mapping_gold.jsonl` |
| Corpus documents with an unknown pricing tier | 89 | `data/specs/manifest.json` |
| Corpus documents that need a key | 87 | `data/specs/manifest.json` |
| Keyless corpus documents (the live probe set) | 11 | `data/specs/probe_set.json` |
| Knowledge-layer tests | 130 | `tests/` |

The graph is built from the 8 seed specs, not all 98 corpus specs. The 916-row
mapping evaluation template also covers the 8 seed tools and has no gold labels
yet, so this repository makes no accuracy or F1 claim. The committed specs are
third-party documents with mixed declared licenses; check
[the corpus note](data/specs/README.md#licensing) before redistributing them.
The pricing tier, access requirement, licence and documentation facts of every
corpus document are extracted deterministically, and a curated entry in
`data/overrides/pricing.yaml` always wins over the extracted value. Every entry
in that file still has an empty `reviewer`, so no licence has been signed off
yet.

## Tests and quality

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app src tests run.py
```

The merged suite holds 261 tests: 130 knowledge-layer tests, 50 application tests, 43
integration tests, 32 Auditor tests and 6 Auditor bridge tests. The application tests cover trust updates and replay, breaker
transitions, ontology links, graph substitutes, all example chains, SQL, document QA,
injected failure substitution, breaker routing, mapper corrections, baselines, the
ranking policy and the HTTP API. The knowledge-layer tests cover the ontology generator, the RDF store and
queries, ingestion of OpenAPI and documents, the vector index and embedder, the Mapper
rules, staging and agent behaviour, the mapping evaluation and an end-to-end run. The
integration tests cover the canonical vocabulary, the RDF ontology bridge, the RDF tool
graph, the knowledge-backed Mapper and the wiring of the backends.

## HTTP API

| Endpoint | Purpose |
|---|---|
| `POST /api/tasks` | Run a task through the Client agent |
| `GET /api/tasks/recent` | Recent task summaries |
| `GET /api/tasks/{id}` | Full task result with trace |
| `GET /api/tasks/{id}/messages` | Persisted agent messages |
| `GET /api/monitoring` | Trust, breakers, drift, Auditor status and provider state |
| `GET /api/auditor` | Auditor catalogue, tool mappings, trust ledger and feed |
| `GET /api/auditor/trust` | Auditor trust leaderboard and feed summary |
| `POST /api/auditor/verify/{tool}` | Verify one catalogue tool (add `?live=true` for a live probe) |
| `POST /api/auditor/monitor/{tool}` | Re-probe one catalogue tool and return drift alerts |
| `GET /api/trust/{provider_id}` | Trust state, history and replay |
| `GET /api/tools` | Tool catalogue with trust and validation |
| `GET /api/ontology` | Concepts, units and capabilities |
| `GET /api/knowledge` | The loaded RDF knowledge layer: graph counts, concepts, tools and artifact paths |
| `POST /api/documents` | Upload a document |
| `POST /api/corrections` | Stage an ontology-checked correction |
| `POST /api/listings` | Ingest a new service listing |
| `POST /api/baselines/{b1,b2}` | Run a baseline |
| `POST /api/demo/fail-next/{tool}` | Schedule a provider failure |
| `POST /api/demo/drift/{tool}` | Inject drift and trip the link |
| `POST /api/demo/trip/{tool}` | Manually trip a breaker |
| `POST /api/demo/reset` | Clear trust, breakers, drift and overrides |
| `GET /api/evaluations` | Evaluation reports |

## Integration hand-off

`app/agents/mapper_stub.py` and `app/agents/auditor_bridge.py` are explicit adapter boundaries:

- The Mapper side of this hand-off is implemented in `app/integration/mapper_adapter.py`: `KnowledgeMapper` keeps the Pydantic contracts in `app/schemas.py` and promotes corrections into the RDF knowledge graph. The stub is still reachable through the `local` backend.
- The Auditor side is implemented by `AuditorBridge`, which delegates catalogue tools to `src/agent_bazaar_auditor` and keeps seeded labels for local-only providers. The Client consumes the same claim labels, confidence signals and drift alerts as before. `AuditorStub` remains the fallback used by the bridge.
- The graph is exposed as Turtle at `data/runtime/knowledge_graph.ttl`; the local ontology and graph classes are the fallback for the concepts and the tools the knowledge layer does not model.

See [docs/integration.md](docs/integration.md) for method-level contracts.

## Push to GitHub

```powershell
git init
git add .
git commit -m "Build Agent Bazaar client, providers, interface and evaluation suite"
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```

Signed-in GitHub CLI users can instead run `gh repo create agent-bazaar --private --source . --remote origin --push`.

## Limitations

- Offline fixtures deliberately exercise only the seeded catalogue; they are not a live-API benchmark.
- GraphRAG has a deterministic TF-IDF fallback when no embedding model or LLM is configured.
- The Auditor is no longer an external placeholder: catalogue tools are checked by `src/agent_bazaar_auditor`, while the SQL, document and adversarial weather providers use the deterministic seeded fallback because the Auditor catalogue does not model them. The Mapper is served by the knowledge layer in the `auto` and the `rdf` backend.
- Trust and breaker state are process-local plus SQLite persistence for trust/traces; breaker state intentionally resets with a new application process.
- The optional LLM is never required for tests, evaluation, or the demo.
- The `app/integration/` bridge is implemented; the `local` backend keeps the original stub behaviour, and the `auto` backend falls back to the stub Mapper when the knowledge-layer artifacts are missing.
- The knowledge-layer graph is built from the 8 seed specifications rather than all 98 corpus specifications.
- The 916-row mapping evaluation template has no gold labels, so the knowledge layer reports no accuracy or F1 figure.
- 89 of the 98 corpus documents have an unknown pricing tier, because their descriptions say nothing about pricing and the rules never guess.
- 11 of the 98 corpus documents are keyless, so the live probe set is one tool short of the 12 to 15 the proposal asks for.
- No corpus tool carries a rating yet (the application's local catalogue does), so the rating factor of the ranking policy is neutral for every corpus tool.
- Every entry in `data/overrides/pricing.yaml` still has an empty `reviewer`, so the licence and terms facts are recorded but not approved.
- The committed specifications are third-party documents with mixed declared licenses; check [the corpus note](data/specs/README.md#licensing) before redistributing them.
