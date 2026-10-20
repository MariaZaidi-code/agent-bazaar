# Agent Bazaar

**Client, Provider and Interface Lead implementation**  
University of Central Punjab - BS Artificial Intelligence  
Rameen Babar

Agent Bazaar is a multi-agent marketplace that finds, verifies, composes, executes and repairs third-party tool chains. A developer asks for a task in natural language; the Client agent retrieves candidate tools with GraphRAG, filters them through a shared ontology, checks claim labels, ranks by trust, validates type and unit links, executes through Provider agents, and substitutes a compatible backup if a provider fails.

The repository is self-contained and runs entirely with free, keyless APIs or deterministic offline fixtures.

## What is included

- **Client agent** with decomposition, GraphRAG retrieval, ontology filtering, claim-aware ranking, dependency-aware composition, type/unit link checks, execution, recovery and answer synthesis.
- **Provider layer** for Open-Meteo, Frankfurter, OpenStreetMap Nominatim, REST Countries, Nager.Date, arXiv, a read-only university SQLite database and uploaded-document question answering.
- **Resilience** with backup mirrors for six live providers, an adversarial Fahrenheit weather mock, trust-weighted ranking, a three-state circuit breaker and circuit-breaker substitution.
- **Trust registry** with Beta-style scoring, signal history, contradiction penalties, demotion and replay verification.
- **Trace viewer** persisting every decision, provider call, verification result and recovery event in SQLite.
- **Responsive web interface** for running chains, inspecting candidates, viewing traces, monitoring trust and breakers, staging corrections, uploading documents and injecting demo failures.
- **Evaluation suite** with 50 matching tasks, 15 chain tasks, B1/B2 baseline comparison, 7 substitution cases, 6 trust scenarios and a seven-configuration ablation.
- **32 automated tests**, Ruff checks and GitHub Actions CI.

## Quick start

### Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe run.py
```

Open <http://127.0.0.1:8000>.

If PowerShell blocks activation, no activation is needed; use the explicit `.venv\Scripts\python.exe` commands above.

### VS Code

1. Open the `agent-bazaar` folder.
2. Run **Python: Select Interpreter** and choose `.venv\Scripts\python.exe`.
3. Open a terminal and run `.\.venv\Scripts\python.exe run.py`.
4. Open port `8000` or browse to <http://127.0.0.1:8000>.

### Configuration

All settings are optional and live in `.env`:

```dotenv
AB_OFFLINE_MODE=true
AB_RUNTIME_DIR=data/runtime
AB_LLM_PROVIDER=none
```

`AB_OFFLINE_MODE=true` is recommended for the first run and for evaluation. Live mode contacts only free, keyless public APIs. Set `AB_OFFLINE_MODE=false` to use them. If a live provider fails, the app falls back to an offline fixture and records the failure.

The optional LLM planner supports OpenAI-compatible providers (`none`, `openrouter`, `groq`, `gemini`). The complete demonstration and evaluation work without an LLM.

## Documentation

- [Architecture and formulas](docs/architecture.md)
- [Agent message protocol](docs/message-protocol.md)
- [Evaluation methodology and results](docs/evaluation.md)
- [Demonstration script](docs/demo-guide.md)
- [Mapper/Auditor integration contracts](docs/integration.md)
- [Requirement-to-code traceability](docs/requirements-traceability.md)

## Five-minute demonstration

1. Run the first example: **Weather + currency**.
2. Inspect the ranked candidates, claim badges, selected tools and the weather/currency chain.
3. Open **Agent trace** and expand an event to see its stored inputs and outputs.
4. Open **Monitoring**, click **Fail next weather call**, then run the weather example again.
5. The primary weather provider fails, the breaker records the failure, the backup mirror executes, and the trace shows `substitution_succeeded`.
6. Click **Inject weather drift**, then run the task again. The backup is selected up front because the primary link is open.
7. Open **Documents**, upload a TXT/MD/CSV/PDF/DOCX file, and ask a grounded question through the Client.
8. Open **Tool library**, submit a correction for the adversarial mock and inspect the staged result.

## Architecture

```text
Developer UI
   |
   v
ClientAgent
   |-- TaskPlanner --------------- deterministic or optional LLM decomposition
   |-- GraphRAGRetriever --------- TF-IDF plus ontology-graph expansion
   |-- Ontology ------------------ concepts, capabilities, units, link checks
   |-- AuditorStub --------------- seeded claim labels, drift alerts
   |-- TrustRegistry ------------- Beta score, history, demotion
   |-- CircuitBreakerRegistry ---- closed / open / half-open
   |-- ProviderRegistry ---------- live providers, mirrors, fixtures
   |
   v
SQLite: traces, trust, cache, documents, university database
```

The execution flow is:

1. Decompose the task into typed sub-goals.
2. Retrieve a candidate list for each capability.
3. Filter candidates through the ontology.
4. Attach claim labels from the Auditor adapter.
5. Rank by `relevance x trust`, with claim and breaker penalties.
6. Select tools and compute dependency-aware input bindings.
7. Reject invalid concept or unit links before execution.
8. Execute in topological order.
9. On failure, select a compatible substitute and retry.
10. Record trust updates, breaker transitions, messages and trace events.
11. Synthesize an answer from successful branch outputs.

See [docs/architecture.md](docs/architecture.md) for the component contracts and formulas.

## Uploaded documents

The document provider accepts `.txt`, `.md`, `.csv`, `.pdf` and `.docx` files up to 10 MB. Text is extracted with `pypdf` or `python-docx`, split into overlapping passages and retrieved with TF-IDF. Answers are extractive and include a source citation. The application seeds a project brief on first run, so document questions work before any upload.

## Evaluation

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

These are deterministic offline results. They exercise orchestration, ontology checks, trust, breakers and recovery against controlled fixtures; they are not a claim about live internet reliability. Live mode is the manual integration check for the public APIs.

## Tests and quality

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\ruff.exe check app tests run.py
```

The tests cover trust updates and replay, breaker transitions, ontology links, graph substitutes, all example chains, SQL, document QA, injected failure substitution, breaker routing, mapper corrections, baselines and the HTTP API.

## Project layout

```text
app/
  agents/        Client, planner, Auditor adapter, Mapper adapter
  baselines/     B1 plain tool-calling and B2 retrieval without graph/ontology
  core/          cache, SQLite, tracing, trust, breakers, LLM, message bus
  data/          ontology, tool catalogue, fixture-backed providers
  evaluation/    datasets, metrics and runnable suites
  knowledge/     ontology, tool graph, GraphRAG retrieval
  providers/     live/fixture provider agents and mirrors
  web/           FastAPI templates and vanilla JS/CSS interface
  config.py      typed settings with environment overrides
  main.py        FastAPI application and API
  schemas.py     message protocol and domain models
  services.py    composition root
docs/            architecture, protocol, evaluation, demo, integration
reports/         generated JSON evaluation reports
tests/           pytest suite
run.py           development entry point
```

## HTTP API

| Endpoint | Purpose |
|---|---|
| `POST /api/tasks` | Run a task through the Client agent |
| `GET /api/tasks/recent` | Recent task summaries |
| `GET /api/tasks/{id}` | Full task result with trace |
| `GET /api/tasks/{id}/messages` | Persisted agent messages |
| `GET /api/monitoring` | Trust, breakers, drift and provider state |
| `GET /api/trust/{provider_id}` | Trust state, history and replay |
| `GET /api/tools` | Tool catalogue with trust and validation |
| `GET /api/ontology` | Concepts, units and capabilities |
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

`app/agents/mapper_stub.py` and `app/agents/auditor_stub.py` are explicit adapter boundaries:

- Replace `MapperStub.submit_correction`, `submit_listing`, `staged` and `reset` with the Knowledge Layer/Mapper implementation while preserving the Pydantic contracts in `app/schemas.py`.
- Replace `AuditorStub.verify`, `inject_drift`, `alerts` and `reset` with the Auditor/Monitoring implementation. The Client already consumes claim labels, confidence signals and drift alerts.
- The graph is exposed as Turtle at `data/runtime/knowledge_graph.ttl`; the local ontology and graph classes are the fallback until the shared RDF graph is connected.

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
- The Mapper and Auditor are adapter stubs owned by other team members; their external implementations should be swapped at the documented boundaries.
- Trust and breaker state are process-local plus SQLite persistence for trust/traces; breaker state intentionally resets with a new application process.
- The optional LLM is never required for tests, evaluation, or the demo.
