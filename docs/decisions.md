# Decisions and known limitations

Status: accepted decisions recorded on 2026-10-20 for the Week 1-2 knowledge
layer and Mapper. Each entry states the context, the decision, alternatives
considered, consequences, and the evidence in this repository. Later changes
should add a new entry rather than rewrite history.

## ADR-001: One RDF graph with SHACL-validated writes

**Context.** Tool discovery needs typed inputs/outputs, subsumption, provenance,
and unit checks. The team also needs a schema that another agent can query without
learning a bespoke API.

**Decision.** Store concepts, units, tools, providers, capabilities, claims, and
mappings in one RDFLib graph serialized as Turtle. Validate every candidate write
against `shapes.ttl` plus deterministic cross-node checks before committing it.

**Alternatives.** A property graph (Neo4j) or relational schema would be faster
for some joins but would require a new ontology/constraint layer and would not
give SHACL validation out of the box. Keeping separate graphs per tool would make
substitution and capability queries harder.

**Consequences.** The graph is portable and inspectable, and invalid writes do
not replace the current graph. The trade-off is RDFLib in-memory performance,
Turtle file persistence, and no transaction log or concurrent-writer support.
The store is a single-process component; `save()` is last-writer-wins.

**Evidence.** `kg/store.py`, `ontology/shapes.ttl`, `tests/test_kg_store.py`,
`data/out/graph.ttl`.

## ADR-002: Frozen upper layer, curated domain seed, optional LLM extension

**Context.** An LLM-generated ontology is useful for long-tail fields but is not
deterministic, may invent units or data types, and depends on quota. A demo must
work offline.

**Decision.** Hand-write and freeze a 12-class upper ontology plus 12 unit
families. Commit 60 curated domain concepts as the offline layer. Permit an LLM
to propose additional concepts only through a sanitized, validated,
violation-driven repair loop. The seed remains the fallback.

**Alternatives.** Pure LLM generation would not be reproducible offline. A large
hand-written ontology would be slow to build and hard to defend. Importing an
existing standard (schema.org, QUDT) was rejected for Week 1 because the mapping
and SHACL layer would need substantial adaptation.

**Consequences.** Coverage is intentionally shallow outside geo, weather,
currency, and general reference. The LLM path can extend coverage but must be
reviewed; generated artifacts are not automatically trusted. The committed
artifact is a seed build, not an LLM build.

**Evidence.** `ontology/upper.ttl`, `ontology/domain.py`,
`ontology/generator.py`, `data/out/ontology.ttl`,
`data/out/logs/ontology_build.json`.

## ADR-003: Units live in code and are emitted as RDF

**Context.** Unit conversion, concept validation, and graph checks must agree.
Duplicating the unit table in Turtle is a drift risk.

**Decision.** Define `UNIT_FAMILIES` once in `ontology/units.py`; generate unit
and family triples with `units_graph()` for the ontology artifact. Unit-bearing
concepts declare a family and default unit; mappings carry a concrete unit.

**Alternatives.** A Turtle-only unit registry would need parsing to convert
values. A third-party units library would add a dependency and still need a
mapping to the ontology. Currency conversion was deliberately left out because
it requires a rate source.

**Consequences.** Conversion is affine and limited to the 12 families. Currency
units are marked non-convertible. A new unit requires a code change and a rebuild.
`CurrencyCode` is currently a child of `CountryCode`; that parent is questionable
and should be reviewed before the domain layer is frozen.

**Evidence.** `ontology/units.py`, `ontology/upper.ttl`,
`tests/test_mapper_rules.py` (unit family checks),
`tests/test_kg_store.py` (invalid unit leaves the graph untouched),
`tests/test_ontology_generator.py` (invalid unit family is sanitised).

## ADR-004: Canonical field path is the join key

**Context.** Ingestion, mapping, correction memory, graph provenance, drift, and
evaluation all need the same stable field identity.

**Decision.** Use
`{direction}.{method}:{endpoint_path}.{local_path}`, composed once in
`ingestion/models.py`. Array traversal uses `[]`; request bodies use `body`;
parameters use `parameters.<name>`. The Mapper infers direction from the prefix
when it is missing.

**Alternatives.** Use a synthetic generated id (loses human readability and
changes when ingestion order changes), or use only the local field name (collides
across endpoints and directions). A JSON Pointer is precise but does not encode
method/endpoint/direction without another convention.

**Consequences.** Paths are readable and stable for the same spec shape. Changing
an endpoint path or field name is a drift event by design. Evaluation ids add the
tool id, so they are not identical to graph field paths.

**Evidence.** `ingestion/models.py:94`, `mapper/rules.py:120`,
`mapper/agent.py:438`, `evaluation/dataset.py:112`.

## ADR-005: Mapping identity is a deterministic hash

**Context.** Re-mapping the same field should update one node, not append a new
node on every run. A tool/field/direction tuple is unique enough for this graph.

**Decision.** Use `ab:mapping-<sha1(tool_id|field_path|direction)[:12]>` as the
mapping IRI.

**Alternatives.** A UUID would always create a new node. A readable IRI
(`tool/field`) would be long and need escaping. An auto-increment id needs a
central counter and makes rebuilds non-deterministic.

**Consequences.** Re-running updates existing nodes, and repeated identical
mappings collapse. The seed run produced 512 mapping results but 467 distinct
nodes; reports must state which number they mean. Twelve hex characters have a
theoretical collision risk that is acceptable at this scale but should be
monitored or lengthened in production. Every seed mapping has two
`ab:recordedAt` values because onboarding updates the mapping and then
`write_tool` adds to the same node; see the graph schema.

**Evidence.** `kg/store.py:109-111`, `data/out/logs/seed_graph.json`,
`tests/test_kg_store.py`.

## ADR-006: Retrieval + LLM with mandatory cache and heuristic fallback

**Context.** Mapping field names to concepts benefits from semantic matching, but
free-tier LLM quotas, network failures, and offline demos are real constraints.

**Decision.** Retrieve top ontology terms and corrections, prompt an LLM with the
candidate set, cache every call on disk by full prompt and schema, and fall back
to a deterministic token-overlap heuristic for the whole batch when the LLM is
unavailable or fails. If the LLM returns a partial batch, missing fields become
unmapped rather than silently switching per field.

**Alternatives.** LLM-only mapping is not reproducible offline. Heuristic-only
mapping is deterministic but weaker semantically. Embedding-only mapping would
not provide a reason or a natural repair signal. Generating concepts on the fly
would make the ontology unstable.

**Consequences.** Results are reproducible when the cache is present. The
heuristic does not use corrections and is weaker on synonyms outside the alias
list. A batch-level failure discards the LLM's successful decisions too. The
cache key includes provider, model, system, user, and schema, so a model change
invalidates the relevant entries.

**Evidence.** `mapper/llm_mapper.py`, `mapper/retriever.py`, `llm/client.py`,
`llm/cache.py`, `tests/test_mapper_agent.py` (FakeLLM mapping with repair,
heuristic mapping, LLM-failure fallback).

## ADR-007: Bounded repair driven by concrete violations

**Context.** LLM mappings can choose a nonexistent concept, the wrong data type,
or an incompatible unit. Re-prompting without feedback is unlikely to converge.

**Decision.** Validate deterministically and with targeted SHACL; send the actual
violation text back to the LLM; allow at most `max_repair_attempts` (default 3),
counting the initial rejected decision as attempt 1. Stop early if no candidate
is returned. If repair fails, record the mapping as unmapped, keep the problems
in the reason, and log for review.

**Alternatives.** Unbounded retries risk loops and cost. A single retry is too
weak for multi-constraint errors. Rule-only correction cannot fix unknown
concepts. Asking the LLM to self-critique without deterministic validation was
rejected because it does not guarantee type/unit correctness.

**Consequences.** Most fixable single-concept errors can be repaired; persistent
errors become review items. The heuristic path has no repair proposer, so its
failures are immediate. `attempts_total` counts only fields that enter repair,
not all mapping attempts. There is no durable review queue.

**Evidence.** `mapper/repair.py`, `mapper/rules.py`, `mapper/agent.py`,
`tests/test_mapper_agent.py` (`test_llm_mapping_with_repair_and_review_queue`).

## ADR-008: Corrections are staged, then learned in context

**Context.** A developer correction should improve future mappings without
letting an unvalidated edit corrupt the graph. The team also needs an audit trail.

**Decision.** Validate a `CorrectionSubmit` against the ontology, stage it, and
promote only valid corrections to `CorrectionMemory` and the correction vector.
Correction memory is retrieved for the LLM prompt on later mappings. Invalid
corrections are rejected; unexpected check/promotion failures become
`pending_review`.

**Alternatives.** Direct graph edits would be simpler but bypass validation and
leave no decision history. Always accepting corrections would poison memory.
Ignoring corrections would lose the learning signal.

**Consequences.** There is an auditable JSONL history and a vector that can be
rebuilt. Corrections do **not** retroactively change existing graph mappings, do
not update a `ToolRecord`, and are ignored by the offline heuristic. Promotion
currently always requires rule validation even though
`promotion_requires_rules_pass` exists as an unused setting. A promotion exception
can occur after the memory append; retrying may duplicate an entry.

**Evidence.** `mapper/staging.py`, `mapper/memory.py`, `mapper/agent.py`,
`tests/test_mapper_staging.py`, `tests/test_mapper_agent.py`
(`test_correction_flow_promotes_rejects_and_feeds_retrieval`),
`tests/test_end_to_end.py`
(`test_correction_staging_and_gated_learning`).

## ADR-009: Drift is a one-field remap, not a full re-onboard

**Context.** The Auditor owns drift detection and sends a `DriftAlert` when a
field's observed values no longer match its description. Re-mapping the whole tool
on every alert would be expensive and could disturb unrelated mappings.

**Decision.** Infer the field type from the new sample, use the old description
for retrieval, remap one field, validate once with no repair loop, and update the
single mapping with `recordedBy="mapper-drift"` and a reason containing old and
new concepts. If the remap fails, mark it unmapped and queue review.

**Alternatives.** Full tool remap is more consistent but costly and noisy. No
automatic remap leaves stale mappings. Multiple repair attempts could hide a
persistent drift problem. Writing a new mapping node would lose identity.

**Consequences.** Drift is cheap and local, but a type change that needs a unit
change may fail and require human review. `evidence` and `detected_by` are not
persisted. Tool descriptions and trust are not updated by drift.

**Evidence.** `mapper/agent.py:434-509`, `tests/test_end_to_end.py`,
`messages/schema.py`.

## ADR-010: Graph queries use explicit subsumption, ranking stays in the Client

**Context.** The Client needs candidate tools by capability and I/O, plus
substitutes. The Mapper and graph should not embed a trust/ranking policy that
belongs to another agent.

**Decision.** Expose small query helpers: capability matching, I/O subsumption,
strict substitute compatibility, field lookup, concept/tool listing, and graph
counts. Return `ToolSummary` with `score=None` and an empty reason; leave trust,
price, execution, and final ranking to the Client.

**Alternatives.** Embedding a ranking score in the graph store would mix policy
with data. A general SPARQL endpoint would be flexible but easier to misuse and
harder to test. Full OWL reasoning was rejected as unnecessary for a shallow
hierarchy.

**Consequences.** The graph API is predictable and testable. `tools_by_io`
treats inputs upward and outputs downward; `compatible_substitutes` is stricter
than a simple "source inputs accepted by candidate" check because it compares all
candidate/source input pairs. Capability match is exact/slug, not semantic.
Callers must not treat `ToolSummary.score=None` as a ranking.

**Evidence.** `kg/queries.py`, `tests/test_kg_queries.py`,
`docs/graph-schema.md`.

## ADR-011: Class-target SHACL plus deterministic checks (performance trade-off)

**Context.** Early SHACL checks used SPARQL-based targets that scanned the graph
for each constraint. On the seed graph, a full validation took roughly 1.7-3.3 s,
which is noticeable in tests and onboarding.

**Decision.** Use `sh:targetClass` shapes for the per-node constraints and move
cross-node checks (duplicate labels/aliases, unit-family declaration, mapping-unit
compatibility) into grouped SPARQL queries and simple loops in `validator.py`.
Run targeted subgraph validation in the Mapper and full validation on commit.

**Alternatives.** Keep SPARQL targets for precision; validate only on save; skip
SHACL and rely on hand-written checks. Each either costs latency, weakens the
guarantee, or duplicates shape logic.

**Consequences.** The earlier development timing recorded about 0.37 s for a full
`KgStore.validate()` on the seed graph, versus about 1.7-3.3 s for the SPARQL-target
formulation. That 0.37 s figure is a project-history measurement on the machine
used at the time; it does **not** reproduce in the current checkout, where the
same command measures roughly 1.3-2.0 s on the committed seed graph
(7,196 triples, 8 tools, 60 concepts, 467 mappings), of which about 1.5-1.7 s is
pySHACL and about 0.2-0.3 s is the deterministic rule checks. The SPARQL-target
shapes are no longer in the repository, so the 1.7-3.3 s comparison cannot be
re-measured here either.

Reproduce the current figure with:

```powershell
python -c "import time; from agent_bazaar.kg.store import KgStore; s=KgStore.build_default(); t=time.perf_counter(); r=s.validate(); print(f'{time.perf_counter()-t:.3f}s conforms={r.conforms} violations={len(r.violations)}')"
```

Treat both numbers as indicative local measurements, not a controlled benchmark.
Re-measure on the target machine and at the full 98-spec graph size before
quoting either. Class targets still visit every node of a targeted class, so at
much larger scale a delta/affected-node validation strategy may be needed. The
trade-off is accepted because correctness is preserved by the deterministic
checks and the graph is small enough for full commits.

**Evidence.** `ontology/shapes.ttl`, `ontology/validator.py`,
`data/out/logs/ontology_build.json`, `tests/test_ontology_generator.py`
(`validate_graph` conformance and duplicate-label assertions).

## ADR-012: Local-first artifacts with simple persistence

**Context.** The project must run on student laptops and in offline demos, with
no paid infrastructure.

**Decision.** Persist the graph and ontology as Turtle, vectors as `.npz` plus
JSONL, corrections/staging as append-only JSONL, and LLM responses as JSON files.
Use the filesystem under `data/` and keep model/vector/cache output out of Git
(except the curated seed and selected graph artifacts).

**Alternatives.** A hosted vector database, PostgreSQL, or a graph server would
add setup and cost. Pickle would be less inspectable and less portable. A single
binary database would hide the append-only audit trail.

**Consequences.** Everything is inspectable and rebuildable, and offline mode
works. There is no locking, transaction log, or multi-writer coordination; do not
run concurrent writers. Vector persistence embeds the dimension in a manifest and
refuses a mismatched load. JSONL readers skip malformed lines silently, which is
convenient but can hide corruption.

**Evidence.** `vec/index.py`, `llm/cache.py`, `mapper/memory.py`,
`mapper/staging.py`, `.gitignore`.

## ADR-013: Evaluation is gated on real labels

**Context.** The evaluation template is ready, but labels are expensive and
pre-labels can bias human annotators. Reporting accuracy on unlabelled data would
be misleading.

**Decision.** Commit an unlabelled template; require two team members to label at
least 40 fields blind (before seeing pre-labels), report Cohen's kappa, and only
then compute accuracy/F1 and the learning curve. Keep dev/test splits and exclude
a correction's own field from held-out evaluation.

**Alternatives.** Use LLM pre-labels as gold (circular), report only qualitative
examples (not reproducible), or evaluate on the seed set used for development
(optimistic). All were rejected.

**Consequences.** No accuracy, F1, or learning-curve number is currently claimed.
`data/eval/mapping_gold.jsonl` has 916 rows and 0 gold concepts. Those 916 rows
come from the 8 seed tools, not from the 98-spec corpus, so a tool-level
dev/test split has very few tools per split and the labelled set would describe
a geocoding/open-data mix rather than the full corpus. The
`run_eval.py` path exits with "dataset has no gold labels yet". The dataset
template currently loses direction (it stores the field path but `to_field_spec`
sets `output`), which should be fixed before the formal evaluation.

**Evidence.** `data/eval/mapping_gold.jsonl`, `evaluation/dataset.py`,
`evaluation/metrics.py`, `evaluation/learning_curve.py`, `scripts/run_eval.py`.

## ADR-014: Seed corpus is small but committed; full corpus is reproducible

**Context.** The full corpus is useful for coverage but large and external. A
reviewer needs a deterministic offline demo.

**Decision.** Fetch about 100 APIs.guru specs with seed 42 and size limits; commit
8 selected seed specs that have outputs, plus their manifest. Keep the full
corpus generated and ignored.

**Alternatives.** Commit all 98 specs (large, licensing/provenance overhead),
download at demo time (network-dependent), or use only hand-written fixtures
(not representative).

**Consequences.** The seed graph covers 8 tools, not the full corpus. Counts in
the seed report are not coverage claims. Upstream changes can alter the selected
list; the manifest and retrieval date are the record. Two specs were skipped in
the current fetch (size or not OpenAPI); only the skip count is printed, and the
reasons are discarded, which weakens reproducibility. The committed seed documents have mixed
declared licenses (including AGPLv3, LGPLv3, custom and public-domain terms);
see `data/specs/README.md` before redistributing them.

**Evidence.** `scripts/fetch_specs.py`, `data/specs/seed/manifest.json`,
`data/specs/manifest.json`, `data/specs/README.md`.

## ADR-015: Keep the Mapper's failure modes explicit

**Context.** Silent fallbacks are convenient in a demo but dangerous in a
marketplace: an unmapped output can make a tool look valid when it is not.

**Decision.** Return structured `MapResult` data with unmapped fields and stats,
record graph-write failures as unmapped, log review events, and expose
`onboard_spec.written` plus `error`. Do not raise ordinary mapping failures to the
caller; raise only programming/ingestion preconditions.

**Alternatives.** Fail the whole request on one bad field (loses useful mappings);
silently drop bad fields (hides coverage loss); write an invalid graph (corrupts
discovery).

**Consequences.** Callers must inspect `written`, `unmapped`, and status. A failed
tool write can occur after mapping commits, so onboarding is not one transaction.
`queued_for_review` is a log counter, not a queue. `pending_review` exists in the
mapping enum but is never assigned.

**Evidence.** `mapper/agent.py:256-364`, `pipeline.py:110-141`,
`tests/test_end_to_end.py`.

## Known limitations and open items

| Item | Impact | Current status / next action |
| --- | --- | --- |
| 916 unlabelled evaluation rows | No accuracy claim possible | Blind double-label at least 40; add dev/test splits |
| Evaluation template covers only the 8 seed tools | Labelled set would not represent the full corpus | Decide between labelling the seed, regenerating the template over `data/specs`, or labelling a stratified full-corpus sample |
| Evaluation template loses direction | Inputs evaluated as outputs | Fix `emit_template`/dataset before formal run |
| `min_confidence` unused | Low-confidence mappings are still written | Wire a threshold or remove the setting |
| `promotion_requires_rules_pass` unused | Setting implies optional gating that does not exist | Implement policy or remove the setting |
| `pending_review` never assigned to `FieldMapping` | Status is misleading | Use it in the Mapper or remove it |
| No durable unmapped-field review queue | Review counter is only logs | Add a JSONL/queue and a resolver API |
| Corrections do not update graph/tool records | A correction is not reflected until a later mapping | Decide whether promotion should also edit the graph |
| Heuristic ignores correction hits | Offline mapping does not learn from corrections | Add deterministic correction lookup |
| `CurrencyCode` parent is `CountryCode` | Semantically wrong hierarchy | Review before freezing domain layer |
| Two `ab:recordedAt` values on all 467 seed mappings | Provenance is ambiguous; the duplicate is an onboarding artifact, not history | Make `_add_mapping` replace timestamps or use an event log |
| 512 vs 467 mapping counts | Reports can look inconsistent | Always label "mapping results" vs "distinct nodes" |
| `demo_mapper.txt` is not generated by the demo | The committed capture is partial (one line) and can mislead | Redirect output explicitly or remove the artifact |
| `ontology_build.json` is overwritten by every build | A small `--limit-specs` review run can replace full-corpus totals | Re-run the full offline build before citing; record the command with results |
| Two fetch skips not persisted | Corpus selection is not fully reproducible | Store skip reasons in the manifest |
| 8-tool graph | No full-corpus graph coverage | Seed all 98 after evaluation and time budget allow |
| No concurrency control | Concurrent writers can lose data | Run one writer; add locking before serving multiple processes |
| No controlled performance benchmark | 0.37 s claim is indicative only | Re-measure with a fixed script and report variance |
| LLM depends on external quota | Demo can fall back silently | Keep cache/offline path; log the actual proposer (the `source` field currently labels fallback mappings `llm` when `use_llm` is true) |
| PDF/DOCX are chunk-only | Not field-mapped | Document limitation; add extraction before claiming coverage |

## References

- Proposal v1.3 and work plan supplied with the project brief.
- [week1-scope-and-protocol.md](week1-scope-and-protocol.md)
- [ontology.md](ontology.md)
- [graph-schema.md](graph-schema.md)
- [mapper-protocol.md](mapper-protocol.md)
- [evaluation-plan.md](evaluation-plan.md)
