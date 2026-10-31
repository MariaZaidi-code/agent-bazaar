# Week 1 scope and shared protocol

Owner: Syeda Maria Batool Zaidi (Knowledge Layer and Mapper Lead).
Project: Agent Bazaar, Proposal v1.3 (15 October 2026).
Repository branch: `maria`.

This document freezes the Week 1 scope for the knowledge layer and Mapper, the
shared message contract, the field-path convention, and the interfaces that other
agents code against. It describes the code in `src/agent_bazaar`; it does not add
APIs.

## 1. Scope

### In scope for this work package

- Upper ontology and units, plus the generated or curated domain layer.
- SHACL shapes, deterministic cross-node rule checks, and the validation wrapper.
- RDF knowledge graph schema, SHACL-validated writes, loaders, and query helpers.
- Vector index over ontology terms, tool descriptions, and stored corrections.
- Deterministic ingestion of OpenAPI JSON/YAML, PDF, DOCX, and text.
- Mapper agent: retrieval, LLM or heuristic mapping, repair, correction staging,
  drift re-mapping, and ToolRecord construction.
- Mapping evaluation dataset template, metrics, learning-curve and ablation
  helpers.
- Documentation and the committed seed corpus.

### Out of scope here (owned by teammates)

- Claim extraction, live probing, and the four claim labels (Qaim, Auditor).
- Rule-based and embedding drift detection that raises `DriftAlert` (Qaim).
- GraphRAG candidate ranking, trust-weighted ordering, chain composition,
  substitution policy, and circuit breakers (Rameen, Client).
- Provider execution, the SQL provider, document provider, trust registry, and
  the web interface (Rameen).
- Paid APIs, local language models, real payments, and probing tools that need
  keys or are rate limited.

This repository currently targets about 100 public API specifications. The
corpus has 98 specification files and 8 committed seed specifications. The graph
artifact is built from the 8 seed tools; loading all 98 is a run-time choice, not
a different schema.

## 2. Deliverables and current evidence

| Deliverable | Location | Current evidence |
| --- | --- | --- |
| Frozen upper ontology | `src/agent_bazaar/ontology/upper.ttl` | 12 upper classes, upper properties, units registry |
| Domain layer | `src/agent_bazaar/ontology/domain.py` | 60 curated concepts (offline fallback and LLM starting point) |
| SHACL shapes and rule checks | `src/agent_bazaar/ontology/shapes.ttl`, `validator.py` | Shapes plus duplicate-label, unit-family, and mapping-unit checks |
| Ontology artifact | `data/out/ontology.ttl` | Offline seed build; upper + units + 60 concepts |
| RDF graph schema and store | `src/agent_bazaar/kg/store.py`, `queries.py` | Validated write, save/load, query helpers |
| Seed graph artifact | `data/out/graph.ttl` | 8 tools written, 512 mapped field results, 557 distinct mapping nodes, 60 concepts |
| Vector index | `src/agent_bazaar/vec/` | Three collections; persisted seed run has 60 ontology terms and 8 tool descriptions |
| Ingestion utility | `src/agent_bazaar/ingestion/` | OpenAPI, PDF, DOCX, text; normalized `NormalizedSpec` |
| Mapper agent | `src/agent_bazaar/mapper/` | MapRequest/MapResult, repair, staging, drift, memory |
| Evaluation template | `data/eval/mapping_gold.jsonl` | 916 unlabelled fields from the 8 seed tools, no gold labels yet |
| Tests | `tests/` | 89 tests pass on this branch |

The difference between 512 mapped field results and 557 distinct mapping nodes is
explained in [graph-schema.md](graph-schema.md): the mapping IRI is a deterministic
hash of `(tool_id, field_path, direction)`, so repeated identical mappings collapse
to one RDF node.

## 3. Roles and handoffs

| Person | Role | Interface this repository provides |
| --- | --- | --- |
| Maria | Knowledge layer and Mapper lead | Ontology, graph, vector index, ingestion, Mapper, mapping evaluation |
| Qaim | Auditor and monitoring lead | `DriftAlert` input, `concept_for_field` lookup, baseline embeddings via `VectorService` |
| Rameen | Client, Provider, and interface lead | Graph queries, `ToolRecord`, `MapResult`, substitution query, tool-description vectors |

Week 1 handoff: agreed protocol draft and tool shortlist. Week 3 handoff: frozen
upper ontology, graph query signatures, embedding function. Week 5 handoff:
loaded graph and a working `MapRequest`/`MapResult` path.

Any change after Week 3 to ontology classes, the embedding model, or a message
schema needs team agreement and a version note.

## 4. Shared message protocol

All messages are Pydantic models derived from `MessageBase` in
`src/agent_bazaar/messages/schema.py:34`. Every message carries:

| Field | Meaning |
| --- | --- |
| `id` | Unique message id; generated with `uuid4().hex` |
| `timestamp` | UTC creation time |
| `sender` | `AgentRole`: mapper, auditor, client, provider, developer, system |
| `correlation_id` | Task trace id; preserved when a request produces a result |
| `message_type` | Read-only property equal to the concrete class name |

`extra="allow"` keeps the protocol forward-compatible. `new_message()` fills
`id` and `timestamp` when a caller constructs a message programmatically.

| Message | Typical direction | Purpose | Mapper support |
| --- | --- | --- | --- |
| `ListingSubmit` | Provider -> Mapper | Tool id, source, format, provider metadata | Handled; requires an ingester |
| `MapRequest` | Client -> Mapper | Tool id and `FieldSpec` list | Handled |
| `MapResult` | Mapper -> Client | `FieldMapping` list, unmapped fields, stats | Produced |
| `CorrectionSubmit` | Developer -> Mapper | Corrected concept/unit and note | Handled through staging |
| `RepairRequest` | Mapper internal | Violation message and rejected mapping | Internal repair loop |
| `DriftAlert` | Auditor -> Mapper | Tool, field, old description, new sample, evidence | Handled; one field re-mapped |
| `Feedback` | Client/Developer -> Mapper | Outcome, rating, optional field | Acknowledged only |
| `TrustUpdate` | Auditor/execution -> registry | Outcome weight | Not handled by Mapper |
| `TaskRequest` | Developer -> Client | Free-text task and constraints | Not handled by Mapper |
| `CandidateList` | Client -> Developer | Ranked candidates | Not handled by Mapper |
| `VerifyRequest` / `VerifyResult` | Client <-> Auditor | Claim verification | Not handled by Mapper |
| `ServiceOffer` | Provider -> Client | Capability and price | Not handled by Mapper |
| `ServiceCall` / `ServiceResult` | Client <-> Provider | Execution | Not handled by Mapper |
| `SubstituteRequest` | Client internal | Replacement query | Not handled by Mapper |

`MapperAgent.handle_message` dispatches `ListingSubmit`, `MapRequest`,
`CorrectionSubmit`, `DriftAlert`, and `Feedback`; unknown messages return
`{"status": "unsupported", "type": ...}` (`src/agent_bazaar/mapper/agent.py:583`).

### Field and mapping payloads

`FieldSpec` is the pre-mapping field view: `field_path`, `name`, `type`,
`description`, `sample_value`, `direction`, `endpoint`, `method`, `required`.
`FieldMapping` is the post-mapping view: `field_path`, `concept`,
`concept_label`, `unit`, `unit_family`, `confidence`, `reason`, `status`,
`attempts`, `source`. Both live in `src/agent_bazaar/messages/schema.py:55-83`.

`MapResult.stats` is an open dictionary. The Mapper currently reports
`mapped`, `unmapped`, `repaired`, `queued_for_review`, `attempts_total`, and
`llm_calls` (`src/agent_bazaar/mapper/agent.py:242-250`).

## 5. Field-path convention

The canonical path is defined once in
`src/agent_bazaar/ingestion/models.py:94`:

```text
{direction}.{method}:{endpoint_path}.{local_path}
```

Examples:

```text
output.get:/v1/forecast.body.temperature_2m
input.get:/v1/forecast.parameters.latitude
output.get:/postcodes/{postcode}.body.schools[].distanceMeters
```

Rules:

- `direction` is `input` or `output`.
- `method` is lower-case in the path (`get`, `post`, ...).
- `endpoint_path` is the specification path, including path parameters.
- `local_path` is dot-separated; array traversal uses `[]`; request bodies start
  with `body`, parameters with `parameters.<name>`.
- `field_path` is the join key across `FieldSpec`, `FieldMapping`,
  `MappedField`, `ab:fieldPath`, evaluation ids, correction memory, and drift.
- The Mapper infers direction from the prefix when a payload omits it
  (`src/agent_bazaar/mapper/rules.py:120`, `agent.py:438`).
- Evaluation ids add the tool id: `{tool_id}:{field_path}`
  (`src/agent_bazaar/evaluation/dataset.py:112`).
- The display name is the last dot segment, not the whole path.

## 6. Frozen interfaces in `protocols.py`

`src/agent_bazaar/protocols.py` contains `runtime_checkable` Protocols and
shared dataclasses. Implementations live in `vec/`, `kg/`, `ingestion/`, and
`llm/`.

| Interface | Methods | Concrete implementation |
| --- | --- | --- |
| `VectorService` | `embed`, `search`, `cosine_distance`, `upsert`, `count` | `vec/index.py:200` (adds `persist`, `load_or_create`) |
| `LLMClient` | `complete_text`, `complete_json`, `stats` | `llm/client.py:51` |
| `Ingester` | `ingest(source, spec_format)` | `ingestion/utility.py:72` |
| `MapperService` | `map_fields`, `submit_correction`, `handle_drift_alert`, `reindex` | `mapper/agent.py:79` |
| `GraphStore` | `write_tool`, `tools_by_capability`, `tools_by_io`, `compatible_substitutes`, `concept_for_field`, `get_concept`, `list_concepts`, `list_tools`, `update_mapping`, `validate`, `save` | `kg/store.py:44` |

Shared dataclasses: `SearchHit`, `IndexItem`, `Violation`, `ValidationResult`;
`IngestionError` carries a machine-readable `code` and `to_dict()`.
Collection names are constants: `ontology_terms`, `tool_descriptions`,
`corrections` (`src/agent_bazaar/protocols.py:18-20`).

## 7. Acceptance criteria

| Area | Criterion | Evidence |
| --- | --- | --- |
| Protocol | Every Mapper message validates as a Pydantic model and keeps `correlation_id` | `tests/test_mapper_agent.py` listing/correlation assertions |
| Ontology | Upper ontology and 60 concepts validate with zero violations | `data/out/ontology.ttl`, `scripts/build_ontology.py --offline` |
| Graph | Writes are all-or-nothing and SHACL-validated | `tests/test_kg_store.py` invalid concept/unit tests |
| Mapper | Mapping, repair, correction gating, and drift work offline | `tests/test_mapper_agent.py`, `tests/test_end_to_end.py` |
| Ingestion | JSON, YAML, PDF, DOCX, and text are covered | `tests/test_ingestion_openapi.py`, `tests/test_ingestion_documents.py` |
| Evaluation | Template exists; no accuracy claim is made before labels | 916 unlabelled rows, 0 `gold_concept` values, 8 tools |
| Quality gate | Full test suite passes | 89 tests |

This is not the full project definition of done. The final graph must also cover
all about 100 specifications, the SQL database, and document services; mapping
accuracy, F1, and the learning curve must be reported; and another team member
must be able to onboard a listing from [onboarding.md](onboarding.md).

## 8. Risks and mitigations

| Risk | Impact | Mitigation now |
| --- | --- | --- |
| Free-tier LLM limits or missing keys | Mapping stalls during a demo | Disk cache, heuristic fallback, seed ontology, offline scripts |
| Ontology is broad but shallow | Weak coverage outside geo/weather/currency/reference | 60 curated concepts, honest limitation, LLM extension path |
| Repair loop does not converge | Fields stay unmapped | Bound at 3 attempts, status `unmapped`, human review queue |
| Embedding model change invalidates drift baselines | Qaim's distances become incomparable | Freeze `BAAI/bge-small-en-v1.5`; hashing fallback; persisted dimension check |
| Label bias or too few labels | Evaluation is not credible | Blind double-labelling of at least 40 fields, Cohen's kappa |
| Upstream APIs.guru list changes | Corpus is not byte-reproducible later | Keep `manifest.json`, committed seed, and seed 42 selection |
| Mapping hash collisions | Fewer graph nodes than mapping results | Deterministic 12-hex digest; count both values in reports |
| No mapped output fields | `ToolShape` rejects the tool | Treat `onboard_spec.written == False` as a review item |
| Unused settings | `min_confidence` and `promotion_requires_rules_pass` are not enforced | Keep defaults conservative; wire before relying on them |

## References

- Message schema: `src/agent_bazaar/messages/schema.py`
- Interfaces: `src/agent_bazaar/protocols.py`
- Field-path convention: `src/agent_bazaar/ingestion/models.py:94`
- Mapper dispatch: `src/agent_bazaar/mapper/agent.py:583`
- Graph schema: [graph-schema.md](graph-schema.md)
- Mapper protocol: [mapper-protocol.md](mapper-protocol.md)
