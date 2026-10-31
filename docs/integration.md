# Integration Hand-off

This document defines the boundaries between the Client/Provider/Interface implementation and the Knowledge Layer/Mapper and Auditor/Monitoring work owned by the other team members.

The runnable adapters are:

- `app/integration/mapper_adapter.py` for the knowledge-backed Mapper, with
  `app/agents/mapper_stub.py` as the local fallback;
- `app/agents/auditor_bridge.py` for the real Auditor package, with
  `app/agents/auditor_stub.py` as the local fallback;
- `app/knowledge/ontology.py` and `app/knowledge/graph.py` for the local
  ontology and catalogue.

They are wired in `app/services.py`. Replacing them should not require changes to the Client loop or the browser code if the contracts below are preserved.

## Composition root

`build_services()` creates one instance of each adapter:

```text
Ontology
ToolKnowledgeGraph
GraphRAGRetriever
AuditorBridge (or the seeded AuditorStub fallback inside it)
KnowledgeMapper (or MapperStub for the local backend)
TaskPlanner
ClientAgent
ProviderRegistry
TrustRegistry
CircuitBreakerRegistry
TraceStore
```

Swap the concrete classes here. Keep `AppServices` fields stable or update every consumer through type checking and tests.

With the `auto` and the `rdf` backend the composition root also builds the knowledge-layer adapters; see [Knowledge layer integration](#knowledge-layer-integration).

## Mapper contract

Current class: `MapperStub` (the `local` backend) or `app/integration/mapper_adapter.py` (the knowledge-backed backend, see [Knowledge layer integration](#knowledge-layer-integration)).

### `submit_listing(request: ListingIngestRequest, correlation_id: str) -> MapResultMessage`

Input:

- `name`, `description`, `capability`;
- typed `inputs` and `outputs` using `ConceptSpec`;
- optional claims and `docs_url`.

Expected behavior:

- map provider fields to ontology concepts and units;
- validate the resulting tool with the shared ontology;
- return `MapResultMessage` with `tool_id`, mapped inputs/outputs, violations, `accepted` and `staged`;
- do not silently accept unknown concepts or units.

The HTTP route is `POST /api/listings`.

### `submit_correction(request: CorrectionRequest, correlation_id: str) -> CorrectionResult`

Input:

- `tool_id`, `field_name`;
- `original_concept`, `corrected_concept`, optional `corrected_unit`;
- developer note.

Expected behavior:

- reject unknown concepts, units or fields;
- stage valid corrections without mutating the live graph;
- return a unique `correction_id`, `accepted`, `staged`, `violations` and a human-readable message.

The HTTP route is `POST /api/corrections`. The UI displays accepted/rejected outcomes.

### `staged() -> dict`

Return both `corrections` and `listings` for inspection. The current UI uses corrections only, but the endpoint contract includes both.

### `reset() -> None`

Clear staged corrections and listings. Called by the demo reset endpoint. It must not clear the production graph.

## Auditor contract

Current class: `AuditorBridge` in `app/agents/auditor_bridge.py`. It delegates
catalogue tools to `src/agent_bazaar_auditor` and keeps `AuditorStub` as the
deterministic fallback for tools the Auditor catalogue does not model.

The application tool id -> Auditor catalogue id mapping is:

| Application tool | Auditor catalogue tool |
| --- | --- |
| `open-meteo-forecast` | `open-meteo` |
| `frankfurter-currency` | `frankfurter` |
| `nominatim-geocode` | `nominatim` |
| `restcountries-facts` | `rest-countries` |
| `nager-holidays` | `nager-date` |
| `arxiv-search` | `arxiv` |

The remaining local providers (`university-sql`, `document-qa` and the
adversarial weather mock) use the seeded labels and injected drift from
`AuditorStub`. The Auditor is synchronous and owns mutable probe baselines, so
`AuditorBridge` runs it in a worker thread and serialises calls with one lock.

### `async verify(task_id, subgoal_id, candidates, correlation_id) -> VerifyResultMessage`

Input:

- the task and sub-goal identifiers;
- a list of `Candidate` objects, each containing a full `ToolSpec`;
- correlation ID.

Expected output:

- `labels`: tool ID -> list of `ClaimVerification`;
- `overall`: tool ID -> one `ClaimLabel`;
- `drift_alerts`: list of alert IDs relevant to this list.

Allowed claim labels:

- `Verified`
- `Supported`
- `Unsupported`
- `Contradicted`

The Client uses `overall` to penalize contradicted candidates and optionally exclude them. `Contradicted` is also a strong negative trust signal.

### `inject_drift(tool_id, reason) -> DriftAlertMessage | None`

Demo-only injection. For a catalogue tool the bridge establishes a healthy
baseline, applies the Auditor mock provider's `rename_field` behaviour, runs
`monitor_tool` and returns the first real drift alert. If the fixture cannot
drift, or the tool is local-only, the seeded `AuditorStub` hook is used. It
must:

- create a high-severity drift alert;
- record a contradiction in the trust registry;
- return `None` for an unknown tool.

### `alerts() -> list[DriftAlertMessage]`

Return active drift alerts for the monitoring endpoint. The bridge merges the
Auditor's converted alerts with the seeded fallback alerts.

### `clear_drift(tool_id) -> bool` and `reset() -> None`

Support demo cleanup. `reset()` clears the bridge's alerts, the Auditor mock
registry, baselines and its trust ledger; the demo reset route intends this.
It must not delete the application's persisted trust history unless explicitly
intended.

### `snapshot() -> list[dict]`

Return serializable alert dictionaries. The monitoring route uses this method.

### Application-facing helpers

`AuditorBridge` also exposes the catalogue directly to the interface:

- `overview()` - catalogue tools, probe coverage, app mappings, trust ledger and feed;
- `verify_tool(tool_id, force_live=False)` - verify one catalogue tool and return both Auditor and app-shaped labels;
- `monitor_tool(tool_id, force_live=False, establish_baseline=False)` - re-probe one tool and return drift alerts;
- `trust_payload()` - leaderboard and feed summary;
- `status()` - mode, catalogue size, mapped tools and alert count.

These back `GET /api/auditor`, `GET /api/auditor/trust`,
`POST /api/auditor/verify/{tool_id}` and
`POST /api/auditor/monitor/{tool_id}`. Add `?live=true` to a verify or monitor
request to force a live probe for that call.

## Knowledge graph contract

The local `ToolKnowledgeGraph` is a fallback for Maria's RDF-backed graph, which is implemented in `app/integration/graph_adapter.py` and described in [Knowledge layer integration](#knowledge-layer-integration). The Client uses:

- `all()`
- `get(tool_id)`
- `by_capability(capability)`
- `neighbors(tool_id, limit)`
- `compatible_substitutes(capability, available_inputs, available_outputs, exclude)`
- `export_turtle(path, trust)`

If the shared graph replaces the local one, preserve these operations or adapt them behind the same class. The retriever also relies on stable `ToolSpec` objects with `id`, `capability`, `inputs`, `outputs`, `keywords` and `search_text`.

The current graph exports Turtle to `data/runtime/knowledge_graph.ttl` at startup. The output includes concepts, tool inputs/outputs, capabilities and trust annotations when available.

## Ontology contract

The RDF-backed implementation of the same operations is `app/integration/ontology_bridge.py`; see [Knowledge layer integration](#knowledge-layer-integration).

The Client calls:

- `exists(concept)`
- `is_subtype(child, parent)`
- `check_capability(tool_capability, required)`
- `check_link(source_concept, source_unit, target_concept, target_unit)`
- `validate_tool(tool)`
- `units_compatible(source, target)`

`check_link` returns `OntologyCheck` with:

- `concept_ok`
- `units_ok`
- `valid`
- `reason`
- optional `conversion` flag

The Client rejects an execution link when `valid` is false. Do not weaken this check without updating the trace and tests.

## Provider registry contract

The Client resolves tools with:

- `by_tool(tool_id)`
- `all()`
- `validation`
- `force_failure(tool_id, times)`
- `reset_demo()`

A provider must expose:

- `tool_id`, `provider_id`
- `spec`
- `async call(params, correlation_id) -> ProviderResponse`
- `status()`
- `force_failure` and `clear_failure`

`ProviderResponse` fields are in `app/providers/base.py`. The Client records `status`, `data`, `error`, `latency_ms`, `cached`, `source`, `warning`, `schema_valid` and `schema_errors`.

## Trust and breaker integration

The Client calls the trust registry directly:

- `record_call(provider_id, success, reason)`
- `record_schema(provider_id, success, reason)`
- `record_probe(provider_id, success, reason)`
- `record_contradiction(provider_id, reason)`
- `get(provider_id)`, `all()`, `history(provider_id)`, `replay(provider_id)`

The breaker registry is:

- `allow(key) -> (bool, state)`
- `record_success(key)`, `record_failure(key)`, `trip(key, reason)`
- `state(key)`, `snapshot()`, `reset()`

Link keys are `client->provider_id`. The UI monitoring table derives its status from these records.

## Interface integration

The browser is intentionally framework-free. It communicates through these JSON endpoints:

- task creation and retrieval;
- monitoring and trust;
- tool catalogue and ontology;
- corrections and listings;
- documents;
- baselines;
- evaluations;
- demo controls.

If an adapter becomes asynchronous over HTTP, keep the endpoint payload shapes or update `app/web/static/app.js` together with the Pydantic response models.

## Knowledge layer integration

The merged repository serves the Client/Provider/Interface layer from the knowledge layer in `src/agent_bazaar`. The bridge lives in `app/integration/` and is selected by the `knowledge_backend` setting.

### Integration modules

| Module | Role |
| --- | --- |
| `canonical.py` | The single translation point between the two vocabularies. It holds the concept, unit and capability alias tables and the list of concepts that only the app models. |
| `ontology_bridge.py` | `KnowledgeOntology` mirrors `app.knowledge.ontology.Ontology` on top of the RDF ontology: subclass closure, unit families and capability canonicalisation, with the local ontology as the fallback for the external concepts. |
| `graph_adapter.py` | `RdfToolGraph` serves the app tool-graph API from the RDF graph and keeps the app's local catalogue as a fallback for the tools that only exist there. |
| `mapper_adapter.py` | `KnowledgeMapper` implements the `MapperStub` API on top of the knowledge-layer `MapperAgent`. Corrections are validated and promoted into the RDF graph instead of only being staged. |
| `messages.py` | Side-effect free conversions between the app schemas and the knowledge-layer message schemas. |

`app/integration/runtime.py` wires the bridge together. `build_knowledge_layer()` loads the published artifacts `data/out/graph.ttl` and `data/out/ontology.ttl` into a `KgStore` and returns the knowledge-layer ontology, graph and Mapper.

### Canonical vocabulary

The concept names of the app are mapped onto the canonical knowledge-layer names:

| App name | Canonical name |
| --- | --- |
| `LocationName` | `PlaceName` |
| `CityName` | `City` |
| `Coordinates` | `Position` |
| `Money` | `MoneyAmount` |
| `Text` | `Description` |
| `Number` | `Count` |
| `DateTimeISO` | `DateTime` |
| `iso8601` | `DateTime` |

The unit names are mapped the same way:

| App unit | Canonical unit |
| --- | --- |
| `C` | `Celsius` |
| `F` | `Fahrenheit` |
| `K` | `Kelvin` |
| `degrees` | `Degree` |
| `deg` | `Degree` |

Capabilities are canonicalised onto the curated taxonomy of the Client layer. The derived slugs of a tool or of a listing are mapped as follows:

| Derived slug | Curated capability |
| --- | --- |
| `weather-api`, `weather-forecast`, `get-weather-forecast`, `forecast`, `weather`, `climate` | `GetWeatherForecast` |
| `geocode-location`, `geocode`, `geocoding`, `location`, `place`, `city`, `address` | `GeocodeLocation` |
| `convert-currency`, `currency`, `exchange-rate`, `money` | `ConvertCurrency` |
| `get-country-facts`, `country`, `country-facts` | `GetCountryFacts` |
| `get-public-holidays`, `holiday`, `holidays` | `GetPublicHolidays` |
| `search-research-papers`, `research`, `arxiv` | `SearchResearchPapers` |
| `query-structured-data`, `structured-data`, `sql` | `QueryStructuredData` |
| `answer-from-document`, `document`, `document-qa` | `AnswerFromDocument` |

A tool whose capability is not in the taxonomy is mapped from its output concepts (`CONCEPT_CAPABILITY` in `app/integration/canonical.py`); a tool that matches no rule is served with the fallback capability `general`.

The concepts that only the app models are listed in `EXTERNAL_CONCEPTS`: `ResearchPaper`, `ResearchTopic`, `NaturalLanguageQuery`, `TabularAnswer`, `DocumentReference`, `DocumentQuestion`, `AnswerFromDocument` and the metadata classes `Entity`, `Service`, `Capability`, `Claim`, `Evidence` and `Provider`. Validation treats them as external rather than invalid, and they are served from the app's fallback ontology `app/data/ontology.json`.

### The `knowledge_backend` setting

`app/config.py` adds the setting `knowledge_backend` with the values `auto` (the default), `rdf` and `local`, plus `knowledge_graph_file` (`data/out/graph.ttl`) and `knowledge_ontology_file` (`data/out/ontology.ttl`). The environment overrides are `AB_KNOWLEDGE_BACKEND`, `AB_KNOWLEDGE_GRAPH_FILE` and `AB_KNOWLEDGE_ONTOLOGY_FILE`.

| Mode | Ontology | Tool graph | Mapper | Knowledge layer |
| --- | --- | --- | --- | --- |
| `auto` (default) | local `Ontology` | local `ToolKnowledgeGraph` | `KnowledgeMapper` | loaded when the artifacts exist |
| `rdf` | `KnowledgeOntology` | `RdfToolGraph` | `KnowledgeMapper` | loaded |
| `local` | local `Ontology` | local `ToolKnowledgeGraph` | `MapperStub` | never loaded |

`auto` keeps the app ontology and the executable tool catalogue and uses the real knowledge-layer Mapper for listings and corrections. When the artifacts are missing, `auto` falls back to `MapperStub` and the application behaves like `local`. In `auto` the promoted listings and the corrections are written to the RDF graph, while the Client keeps reading the local catalogue.

`rdf` serves the whole application from the knowledge layer: the ontology, the tool graph and the Mapper are the RDF-backed implementations and the local classes are used only as a fallback for the tools and the concepts the knowledge layer does not contain. A missing artifact file degrades `rdf` to the local implementations, because the RDF adapters cannot be built without a graph.

`local` keeps the original stub behaviour and never loads the knowledge layer.

### The `/api/knowledge` route

`GET /api/knowledge` reports the RDF layer that is loaded.

| Key | Meaning |
| --- | --- |
| `available` | `true` when the knowledge layer is loaded |
| `backend` | the configured `knowledge_backend` value |
| `graph` | the RDF counts of the graph: tools, concepts, mappings and claims |
| `concepts` | the number of concepts in the RDF ontology |
| `tools` | the tool summaries of the RDF graph |
| `graph_file`, `ontology_file` | the artifact paths that were loaded |

When the knowledge layer is not loaded, the route answers with `available: false`, the configured `backend` and a `reason`.

### Semantic differences

- The knowledge layer renames concepts and units. The app's `C`, `F`, `LocationName` and `Coordinates` are the `Celsius`, `Fahrenheit`, `PlaceName` and `Position` of the RDF ontology. Every value that crosses the boundary is translated by `app/integration/canonical.py`.
- Unit dimensions are family names (`TemperatureUnit`, `AngleUnit`, `CurrencyUnit`) instead of the lowercase dimension strings of the local ontology (`temperature`, `angle`, `currency`).
- The RDF taxonomy is a full transitive closure instead of a single-parent chain. `is_subtype("Temperature", "Entity")` is `False`, because `Temperature` is a subclass of `Concept`, while the external concepts keep the local chain and `is_subtype("ResearchPaper", "Entity")` is `True`.
- The knowledge layer does not model `ISO8601`, `year`, `INR` or `AED`. The local ontology still carries them, so they are only served through the fallback.
- Currency units are not convertible without a live rate, so `units_compatible("USD", "EUR")` reports `(True, False)`, while `C` to `F` reports a conversion as `(True, True)`.

### Message-contract differences

| App contract | Knowledge-layer contract | What the adapter does |
| --- | --- | --- |
| `field_name` | `field_path`, for example `output.temperature_2m` | The adapter resolves the field name against the mappings of the tool in the RDF graph (exact path, field name, mapped concept). When the tool is only known to the local app graph, the path is rebuilt as `input.<name>` or `output.<name>`; when nothing matches, the field name is used verbatim. |
| `original_concept` | no counterpart in `CorrectionSubmit` | The original concept is appended to the note of the submission, so the information stays available to the Mapper and to the auditors. |
| `ConceptSpec` | `FieldSpec` and `FieldMapping` | The app's typed fields are converted to knowledge-layer field specs and back. The declared concept of a field is kept in the description of the field, and a structured `object` or `array` field is typed with the data type of its concept. |
| `accepted` and `staged` | `promoted`, `rejected` and `pending_review` | The status of the knowledge-layer decision is reported in the message and in the staging ledger. A correction is `accepted` only when it is `promoted`; a `pending_review` decision is reported as `staged` but not as `accepted`. |
| `staged` | no counterpart | `staged` keeps the meaning of the stub: the submission is recorded in the staging ledger of the adapter. The knowledge layer promotes a submission right away, so the promotion state is reported in the message and in the ledger instead of in the flag. |
| no graph mutation | `KgStore.write_tool` and `KgStore.update_mapping` | The Mapper now promotes corrections into the RDF knowledge graph instead of only staging them. A listing that fails a rule is rolled back and never reaches the graph. |

## Minimal replacement checklist

1. Implement the adapter class or method.
2. Keep the existing Pydantic return types.
3. Run `pytest` (the integration tests exercise the current contracts).
4. Run the matching, chains, substitution and trust suites.
5. Verify the trace still includes claim, breaker, trust and substitution events.
6. Update `docs/message-protocol.md` only if a payload changes.
7. Do not commit secrets; all default providers are keyless.

## Platform and account integration

The platform layer lives in `app/platform.py` and is composed into `AppServices.platform`.
It is backed by `data/runtime/platform.db` and adds accounts, workspaces, saved tasks,
favorites, workflows, shares, settings, notifications, credentials, analytics, admin
controls and audit logging without changing the existing task or provider contracts.

### Endpoints

- Accounts: `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me`
- Workspaces: `GET /api/workspaces`, `POST /api/workspaces`, `GET/PUT /api/platform/settings`
- Saved work: `GET/POST/DELETE /api/favorites`, `GET/POST/DELETE /api/saved-tasks`, `GET/POST/DELETE /api/workflows`
- History: `GET /api/tasks/recent` now supports `q`, `status`, `capability`, `date_from`, `date_to`, `offset`, `limit`
- Shares and exports: `POST /api/tasks/{task_id}/share`, `GET /share/{token}`, `GET /api/tasks/{task_id}/export?format=json|csv|md|pdf`
- Notifications: `GET /api/notifications`, `POST /api/notifications/read`
- Credentials: `GET/POST/DELETE /api/api-keys`
- Analytics: `GET /api/analytics`
- Admin: `GET/PUT /api/admin/flags/{name}`, `GET/PUT /api/admin/overrides`, `GET/POST/DELETE /api/webhooks`, `GET/POST/DELETE /api/schedules`, `POST /api/schedules/run-due`, `GET/DELETE /api/cache`
- Workspace data: `GET /api/workspace/export`, `POST /api/workspace/import`
- Pages: `/help`, `/settings`, `/analytics`, `/admin`, `/share/{token}`

The middleware in `app/main.py` applies a per-IP rate limit (default 180 requests per
minute) to state-changing API calls and returns a friendly 429 response with
`Retry-After`.

The browser layer is split into `app/web/static/app.js` for the existing experience and
`app/web/static/platform.js` for the platform features. Both load from the same
`ASSET_VERSION` cache key.

## What remains intentionally stubbed

- The Mapper now promotes corrections into the RDF knowledge graph instead of only staging them; the staging ledger of the adapter is a record of what happened, not a queue.
- The local ontology (`app/data/ontology.json`) remains as the fallback for the concepts the knowledge layer does not model yet.
- The Auditor uses seeded claim labels and injected drift rather than independent web/document probes.
- The local graph is not a distributed RDF store.
- The interface has no authentication; it is a local demonstration application. (The platform layer adds a demo account and session cookie, but it is not a production identity system.)

These boundaries are deliberate so the assigned Client/Provider/Interface implementation is runnable without blocking on the other roles.
