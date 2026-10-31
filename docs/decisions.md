# Decisions and known limitations

Status: accepted decisions recorded on 2026-10-20 for the Week 1-2 knowledge
layer and Mapper, and on 2026-10-21 for the API sourcing, quality profiling and
free-first reasoning work. Each entry states the context, the decision,
alternatives considered, consequences, and the evidence in this repository. Later
changes should add a new entry rather than rewrite history.

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
mappings collapse. The seed run produced 606 mapping results but 557 distinct
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
(7,196 triples, 8 tools, 60 concepts, 557 mappings), of which about 1.5-1.7 s is
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

## ADR-016: The free-first tier partition is a sort key, not a factor

**Context.** Proposal Section 7 and NFR1 require that the marketplace prefers
free APIs and never spends money on calls. The commercial tier of a candidate
is one input among several (relevance, trust, documentation quality, mapping
coverage, rating), and a weighted factor cannot express "a free tool is ranked
above a paid one" because any finite weight can be outweighed by a large
relevance or trust value.

**Decision.** The pricing tier is a **partition** applied before the score:
`sort key = (tier_rank, -score, tool_id)` with the canonical order
`free > freemium > paid > unknown`. The score inside a tier remains
`relevance x trust x quality x rating factor`. `pricing_policy="ignore"`
removes the partition, and `tier_order` is configurable.

**Alternatives.** A pricing multiplier or a large additive bonus (rejected:
both can be outweighed, and the behaviour depends on the scale of the other
factors). Sorting only by score and filtering the paid tools out of the list
(rejected: the proposal wants paid tools catalogued and visible). Lexicographic
sorting on a hand-written list of tool ids (rejected: not a policy, and it
would not generalise to new listings).

**Consequences.** A paid tool with the strongest raw score in a task still
sits behind every free candidate, which is the behaviour the proposal asks
for. The partition also means a wrongly classified tool is badly placed: a
free tool classified as `unknown` loses to every classified tool, so the
curated override file matters. The measured effect on the 48-task ranking
dataset: the free-first rate is 1.0000 with the partition and 0.3542 without
it, and the tier separation accuracy is 1.0000 against 0.2292.

**Evidence.** `app/agents/ranking_policy.py` (`tier_rank`, `rank_candidates`),
`app/evaluation/run_ranking.py` (`no_tier` ablation),
`app/evaluation/data/ranking_tasks.jsonl`, `docs/api-sourcing-and-reasoning.md`.

## ADR-017: Paid tools are catalogued but never executed

**Context.** The marketplace should show what exists, including APIs that cost
money, but the project must not incur costs and must not call a service whose
provider did not hand over a credential. A paid API and a keyed API also fail
for different reasons: one for a commercial reason, one for a missing secret.

**Decision.** The graph, the manifest and the shortlist carry paid, freemium
and keyed tools. The executability gate is a boolean on stored facts: a tool may
be executed only when it is free **and** keyless (and, when
`require_known_licence` is enabled, when its licence is known). A
non-executable candidate keeps its position in the shortlist and carries the
reason `not executable: <tier> tier` or `not executable: requires an api key`.
The composition step and the substitution path both apply the gate, so a
non-executable candidate is never called. A `paid_key` access requirement
distinguishes a keyed service that also sells a paid plan from a free service
that merely needs a key.

**Alternatives.** Hiding paid tools entirely (rejected: the proposal asks for
a catalogue, and hiding them removes the reason a developer would look). Let
the ranking decide and call whatever wins (rejected: violates NFR1). Make the
gate an LLM decision (rejected: the gate is a comparison of two stored strings
and must be deterministic).

**Consequences.** The candidate list is honest about what exists while the
project stays free of paid calls. A task whose only free candidates need a
key fails with an explicit reason instead of silently calling a keyed service.
The measured executable-top rate on the ranking dataset is 0.9583: two tasks
have a free but keyed candidate on top, and the Client skips it and continues
down the shortlist.

**Evidence.** `app/agents/ranking_policy.py` (`is_executable`),
`app/agents/client.py` (`_compose`, `_recover`, `_not_executable_reason`),
`src/agent_bazaar/kg/quality.py` (`is_executable`),
`src/agent_bazaar/ingestion/listing_metadata.py` (access requirement),
`tests/test_ranking_policy.py`.

## ADR-018: Ratings come from our own trust registry, never from a marketplace

**Context.** A candidate's reputation could be taken from a public directory,
a marketplace listing or an API review site. Such a number is not reproducible,
is not attributable, cannot be recomputed by a reviewer, and in a marketplace
context it can be gamed. The project also needs a rating that cannot be moved
by one review.

**Decision.** Ratings are produced by this project's own trust registry and
stored on the offering as `ab:ratingValue`, `ab:ratingCount` and
`ab:ratingSource`. The stored value is shrunk towards a Beta prior:
`kg.quality.shrunk_rating(sum, count)` computes `(sum + 0.5 * 2) / (count + 2)`
with a confidence of `count / (count + 2)`, and the caller passes the result to
`KgStore.update_tool_quality(rating_value=..., rating_count=...,
rating_source=...)`. The ranking factor ignores the rating below
`min_rating_count` (default 3) and never drops below `rating_floor` (default
0.5), so one review cannot move the order and a badly rated tool stays visible
behind a better one. Ratings are never scraped from a marketplace or a review
site.

**Alternatives.** Scraping an external rating (rejected: not reproducible, not
attributable, and outside the trust registry the project already owns).
Using the raw average without a prior (rejected: a single review moves the
order). Dropping ratings from the score entirely (rejected: the trust registry
already produces the evidence; only the weighting would be lost).

**Consequences.** The rating starts cold in the corpus: the 98 corpus documents
carry no rating and the committed graph artifact was built before the offering
extension, so the factor is neutral for every corpus tool and the policy
currently ranks on relevance, trust, quality and tier. The application's local
tool catalogue does carry curated ratings for its 9 providers, so the factor is
engaged there. Nothing in this repository wires the trust registry's rating
aggregate into `update_tool_quality()` yet, so those catalogue values are
curated rather than computed. The shrinkage, the minimum count and the floor
are implemented and exercised by the `no_rating` ablation, which moves the MRR
from 1.0000 to 0.9896 on the 48-task dataset. A tool without a rating is
treated as neutral, not as bad.

**Evidence.** `src/agent_bazaar/kg/quality.py` (`shrunk_rating`),
`app/agents/ranking_policy.py` (`rating_factor`),
`src/agent_bazaar/kg/store.py` (`update_tool_quality`),
`app/evaluation/run_ranking.py` (`no_rating` ablation),
`app/core/trust_registry.py`.

## ADR-019: Cross-node invariants are enforced as deterministic rule checks

**Context.** SHACL shapes validate one node against its own class. Several
invariants of the new offering layer span nodes: a tool must not have two
offerings, an offering's tier and access requirement must come from the same
extraction, the facts of a tool must be consistent with the mappings of that
tool. Some of these are expressible as shapes (`ab:ToolOfferingShape` allows at
most one `ab:hasOffering`); others need a rule.

**Decision.** Keep the per-node constraints in `shapes.ttl` and express every
cross-node invariant as a deterministic rule check in Python that runs beside
the shape validation, exactly as ADR-011 did for the unit-family and
mapping-unit checks. The rule is a comparison of stored facts with a defined
outcome, is covered by a test, and never depends on a model. The write path
commits only when the shapes and the rules both pass, so a rejected candidate
leaves the current graph untouched.

**Alternatives.** Express every invariant as a SPARQL-constrained SHACL shape
(rejected: the per-target validation cost is exactly what ADR-011 moved away
from). Validate only on save rather than on every write (rejected: an invalid
graph would then exist in memory). Let the Mapper or the policy repair the
inconsistency silently (rejected: the correction must be visible and the
graph must stay reproducible).

**Consequences.** A violation is reported with the offending node instead of
corrupting the graph, and the same rule runs in the corpus builder, in the
Mapper path and in the evaluation. The cost is that the invariant set is split
between two files, so a new cross-node rule needs both a shape and a rule and
a test for each.

**Evidence.** `src/agent_bazaar/ontology/shapes.ttl` (`ab:OfferingShape`,
`ab:ToolOfferingShape`), `src/agent_bazaar/ontology/validator.py`,
`src/agent_bazaar/kg/store.py` (`_commit`, `_write_offering`),
`src/agent_bazaar/kg/quality.py`, `tests/test_kg_quality.py`.

## ADR-020: The commercial facts are a versioned upper-level extension

**Context.** The upper ontology was frozen at the end of Week 2 with twelve
classes and the domain layer was frozen with 60 curated concepts. The
commercial, access, reputation and documentation facts of a tool need a home in
the graph, but reopening the frozen layer would invalidate the ontology
artifacts, the shapes and the evaluation that were built on top of it.

**Decision.** Add the facts as a versioned **upper-level extension** that
leaves the frozen layer alone: one new class `ab:Offering`, one new object
property `ab:hasOffering` with the domain `ab:Tool` and the range
`ab:Offering`, eighteen new datatype properties
(`ab:pricingTier`, `ab:accessRequirement`, `ab:priceAmount`,
`ab:priceCurrency`, `ab:rateLimit`, `ab:probeBudgetPerMinute`,
`ab:ratingValue`, `ab:ratingCount`, `ab:ratingSource`, `ab:docQuality`,
`ab:docSubScores`, `ab:mappingCoverage`, `ab:licence`, `ab:termsUrl`,
`ab:provenance`, `ab:lastSeen`, `ab:tierEvidence`, `ab:accessEvidence`), and two
new shapes (`ab:OfferingShape`, `ab:ToolOfferingShape`). The 60-concept domain
layer and the minimum shape set are unchanged. A tool has at most one offering.

**Alternatives.** Reopen the frozen upper layer (rejected: the freeze is a
deliverable and the domain artifacts depend on it). Put the facts on the tool
node itself (rejected: the offering is a separate fact bundle with its own
identity and lifetime, and one offering per tool keeps the link explicit).
Keep the facts outside the graph, in the manifest only (rejected: the Client
reads the graph, and a second source of truth would drift).

**Consequences.** The ontology artifacts are extended rather than rewritten, so
the freeze still holds and the existing evaluation stays valid. The new class
is upper level and carries no domain concepts, which means the domain layer
needs no migration. A tool whose access requirement is unknown keeps **no**
offering at all, so the graph never asserts a commercial fact that was not
established. The extension is versioned in the source comment; there is still
no committed graph migration mechanism, so rebuilding from
`scripts/seed_graph.py` remains the reset path.

**Evidence.** `src/agent_bazaar/ontology/upper.ttl` (offering section),
`src/agent_bazaar/ontology/shapes.ttl` (`ab:OfferingShape`,
`ab:ToolOfferingShape`), `src/agent_bazaar/kg/quality.py`
(`offering_iri`, `offering_triples`), `src/agent_bazaar/kg/store.py`
(`_write_offering`), `docs/graph-schema.md`.

## ADR-021: The corpus manifest carries the facts, and a curated file overrides them

**Context.** The corpus builder had to answer three questions that the old
manifest did not hold: what does the API cost, does it need a credential, and
what do its terms say. The answers come from the document itself, so they must
be reproducible; but a rule that reads a pricing page badly would then be
frozen into the corpus, and a human who checked the provider's terms page knows
better than the rule.

**Decision.** Two artefacts, two responsibilities:

- **Manifest v2** (`scripts/fetch_specs.py`, `MANIFEST_VERSION = 2`) records the
  extracted facts of every document next to the descriptive fields, plus
  `source`, `selection_rule_version` and `licence_reviewed_at`. It is
  regenerated deterministically by `--metadata-only` and `--refresh`, and the
  refresh writes a diff (`added`, `removed`, `changed`, `version_changed`) to
  `data/out/logs/corpus_refresh.json`.
- **`data/overrides/pricing.yaml`** holds the human layer. A curated entry
  always wins over the extracted value and carries `reviewer`, `checked_at` and
  `note`. The rules stay in code, the human decisions stay in a file, and the
  manifest records which entries were reviewed through `licence_reviewed_at`.

**Alternatives.** One combined file (rejected: the extracted facts would be
hand-editable, and the diff between rule output and human decision would be
lost). Curated values only in the graph (rejected: the corpus must be
reproducible without the graph). Storing the rules as configuration (rejected:
the rules are code with tests; a configuration file would make them
unreviewable).

**Consequences.** The corpus is reproducible from a seed, and every deviation
from the rule output is visible and attributable. The upstream corpus changes
over time, so the manifest and the refresh report are the record of what was
seen when. `licence_reviewed_at` is empty for every current entry, because no
human has signed the licences off; the facts are recorded, not approved.
Because the rules treat an optional credential parameter as keyless, the
earlier classification of `ideal-postcodes-co-uk` was wrong and the curated
file corrects it to `freemium`/`paid_key`; the same correction removed five
tools from the live probe set.

**Evidence.** `scripts/fetch_specs.py` (`MANIFEST_VERSION`, `manifest_entry`,
`diff_manifests`, `refresh_report`, `select_seed_files`),
`data/overrides/pricing.yaml`, `data/out/logs/corpus_refresh.json`,
`data/specs/probe_set.json`, `src/agent_bazaar/ingestion/listing_metadata.py`,
`tests/test_corpus_sources.py`.

## ADR-022: Adopt the standalone Auditor behind one bridge

**Context.** The Auditor branch was built from the initial commit as a
standalone package with its own `pyproject.toml`, README, docs and tests. It
shares almost no files with the Client/Provider/Interface stack, and several of
its paths collide on a case-insensitive Windows checkout with the existing
`docs/architecture.md`, `docs/evaluation.md` and `tests/test_api.py`. The
Client was written against `AuditorStub`, whose contract returns seeded claim
labels and application-shaped drift messages.

**Decision.** Keep the Auditor as a first-class package under
`src/agent_bazaar_auditor`, install it from the one root `pyproject.toml`, and
move its long-form documents to `docs/auditor/` with unique test module names.
Adapt it through `AuditorBridge` instead of rewriting it into the app. The
bridge maps the six application catalogue tools to Auditor catalogue ids, runs
the synchronous Auditor in a worker thread behind one lock, converts
`ClaimAssessment` and `DriftAlert` objects into the existing `ClaimVerification`
and `DriftAlertMessage` contracts, and records drift as a trust contradiction.
The local SQL, document and adversarial weather providers keep the seeded
`AuditorStub` because the Auditor catalogue does not model them. The
application defaults to fixture mode and optional persistence.

**Alternatives.** Reimplement the Auditor inside `app` (rejected: duplicates a
verified implementation and loses its evaluation). Replace the application
catalogue with the Auditor's 15 tools (rejected: the local SQL, document and
adversarial providers are part of the application's demonstration and
substitution tests). Run the synchronous Auditor directly in the event loop
(rejected: it performs file I/O and owns mutable baselines). Keep the Auditor
as a separate repository (rejected: the brief asks for one integrated
deliverable and one test command).

**Consequences.** The merged suite has one Python requirement (`>=3.11`), one
dependency set and one CLI entry point (`agent-bazaar-auditor`). Six of the
fifteen catalogue tools are verified by the real Auditor; the application's
local-only providers, including the ten Sprint 1 tools, retain deterministic
labels, which is visible in the UI and the bridge tests. The Auditor's own trust ledger and the application trust
registry remain separate but linked by contradiction updates. `demo/reset`
clears both so repeated demonstrations are reproducible.

**Evidence.** `app/agents/auditor_bridge.py`, `app/services.py`,
`app/main.py` (`/api/auditor/*`), `tests/test_auditor_bridge.py`,
`docs/auditor/overview.md`, `docs/architecture.md`.

## ADR-023: Use the redesigned console as the host for the free-first data

**Context.** The Maria branch added pricing tier, access requirement, rating,
documentation quality and executability to the tool payload, and rendered them
in the original table-based console. The Rameen branch replaced that console
with a Figma-matched shell and a different rendering model (marketplace cards,
tool modal and monitor timeline). Merging the JavaScript produced one large
conflict because both branches had rewritten the same result and tool renderers.

**Decision.** Take the redesigned shell as the base and port the free-first
decisions into it rather than keeping two interfaces. Marketplace cards and the
tool modal show tier, access, rating, documentation quality, mapping coverage
and the reason a tool is not executable. The catalogue gains a "Free first"
tier sort, and the monitor metrics show the Auditor mode and the number of
mapped catalogue tools. The old table renderers are removed because the new
shell does not contain their DOM.

**Alternatives.** Keep the old console (rejected: discards the redesign the
team agreed to ship). Merge both consoles behind a toggle (rejected: two
front ends to test and document). Render the free-first data only in the API
(rejected: the interface must explain why a candidate cannot execute).

**Consequences.** There is one browser interface, and every tool view explains
pricing, access and executability. `frontend-preview/` remains a design-only
snapshot with mock data; it is not served by FastAPI and must be updated by
hand if the console changes. The browser layer has no automated DOM test, so a
JavaScript syntax check and the HTTP smoke tests are the current guardrails.

**Evidence.** `app/web/static/app.js`, `app/web/static/styles.css`,
`app/web/templates/index.html`, `frontend-preview/`,
`tests/test_api.py::test_health_and_interface`.

## ADR-024: Make the console an evidence-first "quiet instrument"

**Context.** The merged console exposed the free-first catalogue, but several
backend capabilities were only reachable by calling the API directly: Auditor
verification and monitoring, the Auditor trust leaderboard, trust history and
replay, RDF graph statistics, the Mapper staging ledger, evaluation reports,
persisted task protocol messages and the demo controls. The `/library` route was
still a design-system showcase rather than a product surface. The interface also
used optimistic labels: it could show "Verified" or "Healthy" before a request
had returned, treated a failed request as an empty result, and rendered the
object-shaped `VerifyResult` protocol payload as `[object Object]`. The legacy
stylesheet is large and shared, so a full visual rewrite would have been risky.

**Decision.** Keep `styles.css` as the structural baseline and add
`premium.css` as a second, overriding visual layer loaded after it. Adopt a
"quiet instrument" direction: graphite and warm-paper neutrals, a cobalt accent,
hairline borders, system fonts, tabular numerals, one filled primary action per
view, and no decorative window chrome or offset shadows. Make `/library` the
product-facing **Trust Center** (the route stays for link compatibility) and
expose the evidence surfaces there and in the monitor:

- Auditor mappings, probe definitions, claim counts and mode;
- the trust leaderboard and the current task's typed protocol envelopes;
- RDF graph statistics, the staging ledger and evaluation reports;
- a verification console that calls `/api/auditor/verify` or `/api/auditor/monitor`;
- provider trust state, signal history and ledger replay from `/api/trust/{provider}`;
- demo failure, drift, breaker and reset controls.

Replace the persistent global search field with a command palette
(`Ctrl/Cmd+K`, and `/` when the marketplace search is not focused). Make every
asynchronous surface distinguish loading, empty, error and unavailable states;
only use a success tone when evidence exists. Label unobserved providers as a
default prior, evidence-backed sources as such, staged corrections as awaiting
review rather than rejected, and reset as a two-step action. Summarise
object-shaped Auditor payloads per candidate instead of string-coercing them.
Compute the asset version from static file mtimes so a server restart invalidates
the browser cache.

**Alternatives.** Rewrite the legacy stylesheet (rejected: high regression risk
and a large diff with no product benefit). Keep `/library` as a component
showcase (rejected: it has no user-facing job). Keep a global search box on every
page (rejected: the palette is the single global entry point and `/` remains a
marketplace shortcut). Render optimistic green/healthy states while loading
(rejected: it is untruthful and hides outages). Add a frontend framework
(rejected: the dependency-free layer already works and the remaining work is
presentation and state discipline).

**Consequences.** The visual layer has two CSS files with a deliberate cascade:
`premium.css` must stay after `styles.css`, and new components should be styled
there unless they are structural. The Trust Center is read-only except for
explicit verify/monitor calls and the demo reset. Endpoint failures render as
errors instead of empty lists, so a backend outage is visible rather than
silently looking like a healthy empty system. The `/library` URL remains stable
for existing links, while the page title is now Trust Center. The browser still
has no automated DOM test in the repository; the guardrails are `node --check`,
the HTTP smoke tests and manual Playwright passes.

**Evidence.** `app/web/static/premium.css`, `app/web/static/app.js`,
`app/web/templates/index.html`, `app/main.py` (`ASSET_VERSION`),
`docs/architecture.md#interface`.

## ADR-025: A dedicated documents workspace, explicit document binding and an in-app guide

**Context.** ADR-024 made the console evidence-first, but document question answering still
lived in a modal opened from the top bar. The modal was cramped, listed documents without a
preview or an explicit selection, and the question flow redirected to `/dashboard`. The
answer arrived in the task workspace without the document context, so the user had to find
the document again. Uploaded files could not be deleted from the interface. `/docs` was the
FastAPI Swagger UI, so the URL a user would open for a product guide served the API console
instead, and there was no in-app explanation of the pipeline, documents, trust, shortcuts or
demo limits. The monitor also scattered demo actions, and the verification console required
a manual tool choice before a probe could run.

**Decision.** Split the document workflow from the task workspace and separate the product
guide from the API reference:

- Add `/documents` as a first-class workspace with a document library, upload (TXT, MD, CSV,
  PDF and DOCX up to 10 MB), explicit selection, extracted-text preview, deletion and an
  inline question form. The answer renders on the same page with up to two cited passages
  and an optional link to the full trace; the page never redirects to `/dashboard`.
- Add `GET /api/documents/{document_id}` for metadata and extracted text and
  `DELETE /api/documents/{document_id}` for removal. `POST /api/tasks` accepts an optional
  `document_id` (1 to 80 characters), returns 404 when the id is unknown, and the Client
  threads the id into `AnswerFromDocument` subgoals.
- Keep `/docs` for the in-app Documentation guide (quickstart, pipeline, documents, trust,
  API, shortcuts, troubleshooting and demo limits). Move Swagger UI to `/api/docs`, with
  ReDoc at `/api/redoc` and the OpenAPI document at `/api/openapi.json`.
- Keep `/library` as the Trust Center, add Documents and Documentation to the sidebar and
  command palette, preselect the first mapped tool in the verification console, and group
  demo resets under **Demo utilities**.
- Enforce the 10 MB limit in the API before extraction, keep extraction and retrieval local
  with no external send, and contain deletion: resolve the stored path and unlink it only
  when it is inside the configured uploads directory.
- Describe ratings as ratings in the interface; they remain trust-registry values, not
  marketplace reviews.

**Alternatives.** Keep the modal and the redirect (rejected: the modal hides the extracted
text, the redirect loses the selected document, and the user has to relocate the answer).
Put the workspace on `/dashboard` (rejected: that page already carries the task, candidate,
chain and trace surfaces, and a document question is a separate workflow). Keep Swagger at
`/docs` and move the guide to another path (rejected: `/docs` is the conventional guide URL
for users, while API consumers can use `/api/docs`). Send documents to an external extraction
or LLM service (rejected: the sandbox promises local handling and the project must work
offline without keys). Bind the newest document automatically when no id is supplied
(rejected: the newest file is not necessarily the intended source; explicit ids make a
request reproducible and an unknown id fails loudly). Delete the file before the database row
or trust the stored path (rejected: a failure would leave a visible record with no content,
and a tampered path could reach outside the uploads directory).

**Consequences.** Document questions now have a stable home, a visible selected document and
an answer that keeps its citations and trace link together. The interface has six page routes
and a new guide to keep in sync with the UI. The document API adds two routes, and clients
of `POST /api/tasks` must handle the new optional field and its 404 response. Deletion is
permanent, and because the row is removed before the file unlink and file removal errors are
ignored, an orphaned source file can remain; the containment check still prevents deletion
outside the uploads directory. Documents persist across restarts and are kept by the demo
reset, there is no per-user isolation, and the 10 MB cap is the only size guard. Bookmarks to
the old Swagger URL must move from `/docs` to `/api/docs`. The browser layer still has no
automated DOM test, and the new document detail and delete routes are not yet covered by
route-level API tests.

**Evidence.** `app/main.py` (`/documents`, `/docs`, `/api/docs`, `TaskInput.document_id`,
document routes), `app/agents/client.py` (`document_id` threading),
`app/providers/document_provider.py` (`DocumentStore.delete`),
`app/web/templates/index.html` (Documents and Documentation pages),
`app/web/static/app.js` (document workspace and inline answer),
`docs/architecture.md#interface`, `tests/test_api.py::test_document_upload_and_question`.

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
| Two `ab:recordedAt` values on all 557 seed mappings | Provenance is ambiguous; the duplicate is an onboarding artifact, not history | Make `_add_mapping` replace timestamps or use an event log |
| 606 vs 557 mapping counts | Reports can look inconsistent | Always label "mapping results" vs "distinct nodes" |
| `demo_mapper.txt` is not generated by the demo | The committed capture is partial (one line) and can mislead | Redirect output explicitly or remove the artifact |
| `ontology_build.json` is overwritten by every build | A small `--limit-specs` review run can replace full-corpus totals | Re-run the full offline build before citing; record the command with results |
| Two fetch skips not persisted | Corpus selection is not fully reproducible | Store skip reasons in the manifest |
| 8-tool graph | No full-corpus graph coverage | Seed all 98 after evaluation and time budget allow |
| No concurrency control | Concurrent writers can lose data | Run one writer; add locking before serving multiple processes |
| No controlled performance benchmark | 0.37 s claim is indicative only | Re-measure with a fixed script and report variance |
| LLM depends on external quota | Demo can fall back silently | Keep cache/offline path; log the actual proposer (the `source` field currently labels fallback mappings `llm` when `use_llm` is true) |
| PDF/DOCX are chunk-only | Not field-mapped | Document limitation; add extraction before claiming coverage |
| 89 of the 98 corpus documents have an unknown pricing tier | The tier partition cannot place them | Review the terms pages of the most-used candidates and add curated overrides |
| Only 11 corpus documents are keyless | The live probe set is one tool short of the 12 to 15 the proposal asks for | Add keyless documents to the corpus; no extraction rule can close the gap |
| No rating exists for any corpus tool | The rating factor is neutral for every corpus tool; the application's catalogue does carry curated ratings | Feed the trust registry's aggregate into `ab:ratingValue` and `ab:ratingCount` |
| Every `data/overrides/pricing.yaml` entry has an empty `reviewer` | The licence facts are recorded but not approved; `licence_reviewed_at` is empty throughout the manifest | Name a reviewer per entry and re-check the provider's terms |
| Only six of the Auditor's 15 catalogue tools are mapped to application providers | The local SQL, document and adversarial weather providers still use seeded labels rather than live Auditor evidence | Add catalogue definitions for them or document the fallback in every evidence view |
| The Auditor runs in fixture mode by default | No live provider is contacted unless `AB_AUDITOR_LIVE=true` or `?live=true` is passed | Enable live probes for a verification run when a keyless provider is reachable |
| `frontend-preview/` is a design-only copy | The standalone preview can drift from `app/web` | Regenerate or remove it when the console changes |
| The browser console has no automated DOM test | A runtime JavaScript error would only be caught by the HTTP smoke test or manually | Add a headless browser test for the six page routes |
| New document detail and delete routes lack route-level tests | `GET` and `DELETE /api/documents/{id}`, the unknown-id 404 path and file removal are only checked manually | Add API tests for detail, deletion, 404 and path containment |

## References

- Proposal v1.3 and work plan supplied with the project brief.
- [week1-scope-and-protocol.md](week1-scope-and-protocol.md)
- [ontology.md](ontology.md)
- [graph-schema.md](graph-schema.md)
- [mapper-protocol.md](mapper-protocol.md)
- [api-sourcing-and-reasoning.md](api-sourcing-and-reasoning.md)
- [evaluation-plan.md](evaluation-plan.md)
