# Integration Hand-off

This document defines the boundaries between the Client/Provider/Interface implementation and the Knowledge Layer/Mapper and Auditor/Monitoring work owned by the other team members.

The runnable adapters are:

- `app/agents/mapper_stub.py`
- `app/agents/auditor_stub.py`
- `app/knowledge/ontology.py`
- `app/knowledge/graph.py`

They are wired in `app/services.py`. Replacing them should not require changes to the Client loop or the browser code if the contracts below are preserved.

## Composition root

`build_services()` creates one instance of each adapter:

```text
Ontology
ToolKnowledgeGraph
GraphRAGRetriever
AuditorStub
MapperStub
TaskPlanner
ClientAgent
ProviderRegistry
TrustRegistry
CircuitBreakerRegistry
TraceStore
```

Swap the concrete classes here. Keep `AppServices` fields stable or update every consumer through type checking and tests.

## Mapper contract

Current class: `MapperStub`

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

Current class: `AuditorStub`

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

Demo-only injection. A real Auditor can keep this method or replace it with a test hook. It must:

- create a high-severity drift alert;
- record a contradiction in the trust registry;
- return `None` for an unknown tool.

### `alerts() -> list[DriftAlertMessage]`

Return active drift alerts for the monitoring endpoint.

### `clear_drift(tool_id) -> bool` and `reset() -> None`

Support demo cleanup. `reset()` must not delete persisted trust history unless explicitly intended.

### `snapshot() -> list[dict]`

Return serializable alert dictionaries. The current monitoring route uses `alerts()` plus Pydantic serialization.

## Knowledge graph contract

The local `ToolKnowledgeGraph` is a fallback for Maria's RDF-backed graph. The Client uses:

- `all()`
- `get(tool_id)`
- `by_capability(capability)`
- `neighbors(tool_id, limit)`
- `compatible_substitutes(capability, available_inputs, available_outputs, exclude)`
- `export_turtle(path, trust)`

If the shared graph replaces the local one, preserve these operations or adapt them behind the same class. The retriever also relies on stable `ToolSpec` objects with `id`, `capability`, `inputs`, `outputs`, `keywords` and `search_text`.

The current graph exports Turtle to `data/runtime/knowledge_graph.ttl` at startup. The output includes concepts, tool inputs/outputs, capabilities and trust annotations when available.

## Ontology contract

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

## Minimal replacement checklist

1. Implement the adapter class or method.
2. Keep the existing Pydantic return types.
3. Run `pytest` (the integration tests exercise the current contracts).
4. Run the matching, chains, substitution and trust suites.
5. Verify the trace still includes claim, breaker, trust and substitution events.
6. Update `docs/message-protocol.md` only if a payload changes.
7. Do not commit secrets; all default providers are keyless.

## What remains intentionally stubbed

- The Mapper does not promote corrections into the production graph or learn embeddings.
- The Auditor uses seeded claim labels and injected drift rather than independent web/document probes.
- The local graph is not a distributed RDF store.
- The interface has no authentication; it is a local demonstration application.

These boundaries are deliberate so the assigned Client/Provider/Interface implementation is runnable without blocking on the other roles.
