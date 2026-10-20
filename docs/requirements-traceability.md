# Requirements Traceability

The requirement labels below are taken from the proposal's functional and non-functional requirement list. This repository covers the Client, Provider and Interface scope in full and provides adapter coverage where another role owns the implementation.

## Functional requirements

| Requirement | Coverage | Implementation | Verification |
|---|---|---|---|
| FR1: ingest a provider specification or document and produce ontology-mapped fields | Adapter | `POST /api/listings`, `MapperStub.submit_listing`, `Ontology.validate_tool` | `test_api.py`, `test_ontology_graph.py` |
| FR2: learn from corrections and apply them to later mappings | Partial adapter | Corrections are validated and staged in `MapperStub`; promotion/learning belongs to the Mapper | `test_client_integration.py`, UI correction flow |
| FR3: given a task, return a ranked candidate list with reasons | Complete | `ClientAgent._candidates`, GraphRAG retrieval, ontology filters, claim labels, trust score, reasons | 50-task matching suite, `test_client_integration.py` |
| FR4: label every claim Verified, Supported, Contradicted or Unsupported | Adapter plus UI | `AuditorStub.verify`, `ClaimLabel` schema, candidate claim badges | `test_client_integration.py`, API/UI |
| FR5: build multi-step chains valid only if output types and units match the next input | Complete | `ClientAgent._compose`, `_link_checks`, `Ontology.check_link`, input bindings | 15 chain tasks, ontology tests |
| FR6: maintain and update a trust score for each provider | Complete | `TrustRegistry`, Beta score, weighted signals, history, replay, demotion | trust suite, trust tests |
| FR7: re-probe tools and raise drift alerts when mappings change | Client side plus demo adapter | `AuditorStub.inject_drift`, drift alerts, breaker trip, tracing | demo drift test, monitoring UI |
| FR8: substitute a compatible tool when a tool fails or trust falls | Complete | `ClientAgent._recover`, `ToolKnowledgeGraph.compatible_substitutes`, mirrors | 7-case substitution suite |
| FR9: provide a web interface for the developer flow | Complete | FastAPI + Jinja2 + vanilla JS/CSS | HTTP UI tests, Uvicorn smoke test |
| FR10: stage corrections until checks pass | Adapter | `MapperStub.submit_correction`, `/api/staged` | correction tests |
| FR11: compare probe responses with baseline embeddings | Not owned | Auditor/Mapper integration point; demo uses injected drift | documented gap |
| FR12: return violations for bounded repair attempts | Partial adapter | `MapResultMessage.violations` and `RepairRequestMessage`; no automatic repair loop | schema/API tests |
| FR13: trip a circuit breaker on a failing Client-to-Provider link | Complete | `CircuitBreakerRegistry` closed/open/half-open, failure threshold, cooldown, manual trip | breaker tests, monitoring API |
| FR14: show a decision trace in the interface | Complete | `TraceStore`, trace viewer, `/api/tasks/{id}`, `/messages` | trace tests, UI |

## Non-functional requirements

| Requirement | Coverage | Evidence |
|---|---|---|
| NFR1: free resources only, no paid APIs or local model | Complete | Keyless providers, fixtures, optional off-by-default LLM |
| NFR2: cache LLM/API responses | Complete | `Cache`, provider cache keys, LLM cache |
| NFR3: report probe coverage and results honestly | Complete | `docs/evaluation.md` states fixture limitations and negative controls |
| NFR4: every decision explainable from stored evidence | Complete | Trace events, candidate reasons, trust history, breaker transitions |
| NFR5: agents independent, structured messages | Complete | Pydantic message envelope, `MessageBus`, adapter boundaries |

## Deliverable status

| Deliverable | Status |
|---|---|
| Client agent with GraphRAG matching and ontology filtering | Complete |
| Type/unit-checked composition and execution | Complete |
| Provider wrappers for weather, currency, geocoding, countries, holidays, arXiv, SQL and documents | Complete |
| Trust registry with update history and demotion | Complete |
| Circuit breaker and compatible substitution | Complete |
| Trace viewer and developer interface | Complete |
| Baselines B1 and B2 | Complete |
| Matching dataset (~50 tasks) | 50 tasks / 67 expected links |
| Chain evaluation (~15 tasks) | 15 tasks |
| Substitution, trust and ablation evaluation | Complete |
| Integration adapters for Mapper and Auditor | Complete, deterministic stubs |

## Intentionally external

- The real Auditor's scheduled probes, claim verification against external evidence, and embedding-based drift comparison.
- The real Mapper's promotion of staged corrections into the production graph and learning step.
- Distributed/shared RDF graph hosting.
- Authentication and multi-user deployment; this is a local demonstration application.
