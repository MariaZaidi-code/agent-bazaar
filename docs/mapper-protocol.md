# Mapper protocol

The Mapper turns normalized fields into concept mappings. It retrieves ontology
terms and past corrections, asks an LLM (or uses a deterministic fallback),
checks types and units, repairs rejected mappings within a bound, writes valid
mappings to the graph, and returns a `MapResult`. Invalid graph writes are
reported, not raised to the caller.

Code: `src/agent_bazaar/mapper/agent.py` (orchestration),
`mapper/llm_mapper.py` (prompt and heuristic mapper), `mapper/retriever.py`,
`mapper/rules.py`, `mapper/repair.py`, `mapper/staging.py`, `mapper/memory.py`.
Messages: `src/agent_bazaar/messages/schema.py`.

## 1. Request and response

### Minimal `MapRequest`

```json
{
  "tool_id": "open-meteo",
  "fields": [
    {
      "field_path": "output.get:/v1/forecast.body.current.temperature_2m",
      "name": "temperature_2m",
      "type": "float",
      "description": "Air temperature at 2 metres",
      "sample_value": 17.4,
      "direction": "output"
    },
    {
      "field_path": "input.get:/v1/forecast.parameters.latitude",
      "name": "latitude",
      "type": "float",
      "description": "Latitude",
      "sample_value": 52.52,
      "direction": "input"
    }
  ]
}
```

Defaults fill `id`, `timestamp`, `sender=system`, and `correlation_id`. The
canonical field-path rules are in
[week1-scope-and-protocol.md](week1-scope-and-protocol.md#5-field-path-convention).
`options` is accepted but not read by the current Mapper.

### Typical `MapResult`

```json
{
  "tool_id": "open-meteo",
  "mappings": [
    {
      "field_path": "output.get:/v1/forecast.body.current.temperature_2m",
      "concept": "https://agent-bazaar.local/ontology#Temperature",
      "concept_label": "Temperature",
      "unit": "Celsius",
      "unit_family": "TemperatureUnit",
      "confidence": 0.86,
      "reason": "token overlap ...",
      "status": "mapped",
      "attempts": 0,
      "source": "llm"
    }
  ],
  "unmapped": [],
  "stats": {
    "mapped": 1,
    "unmapped": 0,
    "repaired": 0,
    "queued_for_review": 0,
    "attempts_total": 0,
    "llm_calls": {}
  }
}
```

`MapResult` inherits `id`, `timestamp`, `sender`, and `correlation_id` from
`MessageBase`; the Mapper copies `request.correlation_id`, so a request and its
result share a trace id. The Mapper does not explicitly set `sender`, so the
serialized response keeps the default `system` sender.

### Which fields appear where

- `unmapped` contains every `FieldSpec` with no successful mapping.
- `mappings` contains successful mappings **and** failure records with
  `status="unmapped"` when a decision was made but repair or graph validation
  failed. Fields rejected immediately by the provider (`decision.unmapped` or no
  decision) appear only in `unmapped`, not in `mappings`.
- Consumers must filter `status != "unmapped"` before treating entries as
  mappings. `listing_to_tool_record()` does this.
- `stats["mapped"]` counts only mappings committed to the graph; it does not
  count failed/queued entries.

## 2. Preconditions and side effects

- `MapperAgent` needs a `GraphStore`, a `VectorService`, and optionally an
  `LLMClient` and ingester. `build_index()` is called lazily on first mapping.
- The index covers concepts from `store.list_concepts()`, corrections from
  `CorrectionMemory`, and (for retrieval) nothing else. Tool descriptions are not
  used for field mapping.
- `map_fields()` writes each valid mapping through
  `store.update_mapping()`. It can create a mapping and link it to a Tool IRI
  even if that Tool node has not been written yet. The caller is responsible for
  writing the ToolRecord (`pipeline.onboard_spec` or `store.write_tool`).
- Onboarding is not a single transaction: `map_fields` commits mappings, then
  `write_tool` validates and commits the tool. If `write_tool` fails, mapping
  nodes already committed remain. Treat a failed onboard as a partial write and
  inspect/rebuild the graph.
- `handle_listing_submit` ingests and maps only; it does not write a ToolRecord.
  It also ignores provider fields on `ListingSubmit` except the source/format
  passed to the ingester.
- An initial unmapped field does not remove an older mapping for the same field.
  Re-mapping a field that fails can leave the previous graph mapping in place.

### `handle_message`

`MapperAgent.handle_message` supports `ListingSubmit`, `MapRequest`,
`CorrectionSubmit`, `DriftAlert`, and `Feedback`
(`agent.py:583-594`). Feedback is acknowledged with
`{"status": "recorded", "tool_id": ...}` and is not persisted. Other messages
return `{"status": "unsupported", "type": ...}`.

## 3. Mapping pipeline

1. **Ensure index.** Build concept and correction vectors once.
2. **Retrieve.** For each field, build a query from name, type, description, and
   sample value. Search `ontology_terms` for `top_k_terms` (default 12) and
   `corrections` for `top_k_corrections` (default 8).
3. **Propose.**
   - If an LLM client is configured and `use_llm` is true, send one batch prompt
     containing every field, its candidates, and correction lines. The prompt
     requires one `LLMDecision` per field.
   - If no client, provider is `offline`, `use_llm=False`, or the LLM call fails
     with `MappingLLMError`, use the heuristic mapper.
   - If the LLM returns a partial batch, missing fields become unmapped; there
     is no per-field fallback to the heuristic.
4. **Resolve concept.** Match the decision's concept by full IRI, label, local
   name, or alias, case-insensitively. An unknown concept is a validation
   problem.
5. **Validate.** Apply deterministic type and unit rules and a targeted SHACL
   check for the mapping node.
6. **Repair if needed.** Run the bounded repair loop. Only the LLM path supplies
   a repair proposer; the heuristic path has no retry and fails immediately.
7. **Persist.** Call `update_mapping` with provenance. A graph validation error
   turns the field into an unmapped failure record and increments
   `queued_for_review`.
8. **Return.** Fill stats and `correlation_id`; do not raise mapping failures.

### LLM prompt

The system prompt instructs the model to pick exactly one concept when one fits,
use only a unit from the concept's family, give confidence in `[0, 1]`, and set
`unmapped` only when nothing fits. The user payload contains the tool id and, per
field: path, name, type, description, sample value, top ontology candidates
(label, IRI, type, unit family), and stored correction lines. The response model
is `LLMDecisionBatch` (`llm_mapper.py:35-38`).

Caching is handled by `LLMClient.complete_json(..., use_cache=True)`; the cache
key includes provider, model, system, user, and schema. A repeat run can replay
the same decisions without a network call. A cache miss with no key and an
offline provider fails, then falls back to the heuristic.

### Heuristic fallback

The fallback tokenizes the field name and description and compares with each
concept's label, local name, and aliases. It ignores stopwords and tokens shorter
than three characters, computes overlap relative to the smaller token set, and
adds a bonus for an exact normalized name match (0.4) or alias match (0.2). The
best score must be at least 0.34; otherwise the field is unmapped. Confidence is
`min(0.9, 0.4 + score)`, rounded to two decimals. Unit-bearing concepts get
their default unit. The fallback does not use retrieved corrections.

## 4. Deterministic rules

### Type compatibility

`TYPE_COMPATIBILITY` in `mapper/rules.py:19-28` maps the concept's declared data
type to the field types it accepts:

| Concept type | Accepted field types |
| --- | --- |
| `integer` | integer |
| `float` | integer, float |
| `string` | integer, float, string, date, datetime, boolean |
| `boolean` | boolean |
| `date` | string, date |
| `datetime` | string, date, datetime |
| `array` | array |
| `object` | string, array, object |

An unknown concept type is treated as compatible. The field type is normalized
to lower-case and defaults to `string`. This is intentionally permissive: an
integer is accepted for a string, and a string is accepted for an object; the
rule prevents clearly impossible mappings, not every semantic mismatch.

### Unit rules

- A unit-bearing concept requires a non-empty mapping unit.
- The unit must exist in `UNIT_FAMILIES`.
- It must belong to the concept's family.
- A non-unit-bearing concept may not carry a unit.
- Confidence must be within `[0, 1]`.

Repair clamps candidate confidence to `[0, 1]`; an invalid confidence on the
first decision counts as a problem and triggers repair when available.

### Targeted SHACL

`validate_mapping_shacl()` builds a small graph containing the concept (with
label, type, parent, data type, unit family) and the mapping node, then runs the
normal shapes. It does not mutate the store. The full graph is validated again
when `update_mapping` commits.

## 5. Repair loop

- `MapperSettings.max_repair_attempts` defaults to 3 and is floored at 1.
- The initial rejected decision counts as attempt 1. With the default, there are
  at most two additional proposals.
- Each `RepairRequest` carries the field path, the joined violation text, the
  rejected mapping, and the attempt number. Its `tool_id` is set to `""` by the
  loop; the orchestration already knows the tool.
- The repair proposer re-prompts the LLM with the violation hint, resolves the
  concept, reapplies the default unit, and marks the candidate `repaired`.
  `reason` includes `repair hint: ...`.
- If the candidate is `None`, the loop stops early. If all attempts fail, the
  outcome carries the last problems and no mapping; the orchestrator records an
  `unmapped` mapping with those problems and queues review.
- Heuristic mappings cannot be repaired because `_repair_proposer` returns
  `None` when the LLM is not in use.

Attempt accounting is local: `attempts_total` sums `outcome.attempts` only for
fields that entered repair. Clean fields do not add an attempt, and a heuristic
failure that never produces a candidate may record attempt 1 with no retry.

## 6. Corrections and review

### Correction flow

`CorrectionSubmit` -> staging check -> promote to `CorrectionMemory` and the
corrections vector.

- Validation resolves the corrected concept and checks the unit against that
  concept. Unknown concepts/units are rejected. A unit is required when the
  concept is unit-bearing and forbidden when it is not.
- An exception in the check or promotion step produces `pending_review`; a
  normal validation failure produces `rejected`; a successful promotion produces
  `promoted`.
- Only the newly promoted entry is upserted into the corrections vector.
- Promotion records the correction but does **not** update the existing graph
  mapping or any `ToolRecord`. The correction affects future mappings through
  retrieval (LLM prompt) and memory; it is not a retroactive graph edit.
- The offline heuristic ignores correction hits, so promoted corrections do not
  change heuristic decisions.
- `staging.stats()` reports submitted, promoted, rejected, and rejected share.
  It does not report a pending count; use `staging.pending()`.
- `promotion_requires_rules_pass` exists in settings but is not consulted;
  promotion always requires the validation check to return no problems.

The staging JSONL record is `{ "decision": {...}, "correction": {...} }`.
Corrections are `data/memory/corrections.jsonl` entries with tool, field,
corrected concept/unit, note, submitter, timestamp, and `status="promoted"`.

### Review

Unmapped fields increment `queued_for_review` and emit `unmapped` /
`queued_for_review` events to the Mapper log. There is no durable review queue for
fields and no API to claim or resolve a review item. The only persisted queue is
the staging queue for corrections. Do not describe `queued_for_review` as a
database-backed queue.

## 7. Drift re-mapping

`DriftAlert` triggers a single-field remap, not a full tool remap:

1. Direction is inferred from the field path (`input.` or otherwise `output`).
2. The new field type is inferred from `new_sample`; `old_description` becomes
   the description.
3. The field is retrieved and proposed like a normal mapping.
4. The decision is validated once. There is no repair loop. An unmapped or
   invalid decision is queued for review.
5. The old concept is read with `concept_for_field` before the write.
6. `update_mapping` writes the new concept and sets status `drift_remapped`,
   `recordedBy="mapper-drift"`, and a reason containing old and new concepts.
7. `DriftAlert.evidence` and `detected_by` are accepted but not persisted.

A drift write updates one mapping node. It does not change the tool's spec,
tool description vector, claims, or trust.

## 8. Stats and statuses

| Stat | Meaning |
| --- | --- |
| `mapped` | Successful graph writes |
| `unmapped` | Fields with no successful mapping, including decision failures |
| `repaired` | Mappings that succeeded after at least one failed validation |
| `queued_for_review` | Failures logged for review; not a durable queue |
| `attempts_total` | Repair-loop attempts only |
| `llm_calls` | Snapshot of `client.stats` if available, else `{}` |

| Status | Set by | Meaning |
| --- | --- | --- |
| `mapped` | Initial mapping | Validation passed and write committed |
| `repaired` | Repair success | A repaired candidate passed validation |
| `unmapped` | Orchestrator | Decision/repair/graph write failed |
| `drift_remapped` | Drift handler | Drift update committed |
| `pending_review` | Enum only | Defined in `FieldMappingStatus`, not emitted by the Mapper |

`source` is one of `llm`, `fallback`, or `drift` in the current flow. It is
selected from `use_llm` before proposal, so an LLM-configured run that silently
falls back to the heuristic still labels those mappings `llm`. The enum also
permits `correction` and `rule`, but the Mapper does not emit them.

## 9. Configuration and operational notes

Defaults and `config/settings.yaml`:

| Setting | Default | Used |
| --- | --- | --- |
| `mapper.max_repair_attempts` | 3 | Yes |
| `mapper.top_k_terms` | 12 | Yes |
| `mapper.top_k_corrections` | 8 | Yes |
| `mapper.min_confidence` | 0.0 | No |
| `mapper.promotion_requires_rules_pass` | true | No |
| `llm.provider`, `llm.model` | provider/model in config | LLM client only |
| `llm.temperature` | 0.0 | LLM client |
| `llm.timeout_s`, `llm.max_retries` | 90, 3 (code defaults) | LLM client |

`config/settings.example.yaml` selects Groq. The local, gitignored
`config/settings.yaml` may override the provider and model; in this checkout it
selects Gemini, so an LLM run needs `GEMINI_API_KEY` in the process environment.
Because that file is not committed, other checkouts will use the code defaults
in `src/agent_bazaar/config.py` unless they copy the example. `--offline` modes
and missing/offline clients use the heuristic. The current code contains no
paid-tier requirement, but an LLM provider may impose its own quota.

Failure behaviour:

- LLM batch failure -> one log event and heuristic fallback for the whole batch.
- Unknown concept -> validation failure, repair, then unmapped/review.
- Invalid graph write -> unmapped failure record; current graph unchanged for
  that update.
- No ingester on `ListingSubmit` -> `ValueError`, not a result.
- Empty field list -> `MapResult` with empty mappings and zero stats; no LLM call.

## 10. Consumer checklist

1. Preserve `correlation_id` and ignore `sender=system` unless you set it.
2. Filter `mappings` to statuses other than `unmapped`; do not count raw
   `mappings` length as a success count.
3. Use `unmapped` as the review input.
4. Call `store.write_tool()` / `onboard_spec()` to materialize the tool; mapping
   alone does not create a typed Tool or output links sufficient for discovery.
5. Pass `direction` in provenance so `update_mapping` can find the right mapping.
6. Treat onboarding as multiple commits; on `written=False`, inspect whether
   mapping nodes were already added.
7. Do not assume corrections retroactively change graph mappings or heuristic
   decisions.
8. Do not use `min_confidence` or `promotion_requires_rules_pass` as enforced
   policy until the corresponding code path exists.

## 11. Known gaps

- `FieldMappingStatus.PENDING_REVIEW` is not assigned to mappings; review is
  logged only.
- `min_confidence` and `promotion_requires_rules_pass` are unused.
- Corrections are not applied deterministically and do not update the graph.
- The heuristic ignores corrections.
- Initial unmapped results do not delete stale mappings.
- `attempts_total` excludes initial attempts.
- `MapRequest.options` is ignored.
- `FieldMapping.source` does not distinguish an LLM failure from a successful
  LLM proposal when `use_llm` is true.
- `ListingSubmit` provider metadata is ignored by `handle_listing_submit`.
- Feedback is not persisted.
- Drift evidence is not persisted.
- No concurrency control around the in-memory graph or JSONL files.

## References

- Mapper orchestration: `src/agent_bazaar/mapper/agent.py`
- Prompt/heuristic: `src/agent_bazaar/mapper/llm_mapper.py`
- Retrieval: `src/agent_bazaar/mapper/retriever.py`
- Rules: `src/agent_bazaar/mapper/rules.py`
- Repair: `src/agent_bazaar/mapper/repair.py`
- Staging and memory: `src/agent_bazaar/mapper/staging.py`, `memory.py`
- Message models: `src/agent_bazaar/messages/schema.py`
- Graph writes: `src/agent_bazaar/kg/store.py`
- Onboarding wrapper: `src/agent_bazaar/pipeline.py`
- Tests: `tests/test_mapper_agent.py` (LLM mapping with repair, heuristic
  fallback, LLM failure fallback, correction flow, drift remap, listing submit),
  `tests/test_mapper_rules.py` (type table, unit rules, targeted SHACL,
  correction validation), `tests/test_mapper_staging.py` (staging queue and
  statistics), `tests/test_end_to_end.py` (onboard, map, query, correction
  gating, drift).

There is no separate `test_repair.py`, `test_correction_memory.py`,
`test_staging.py`, or `test_llm_mapper.py`; the repair loop, correction memory,
staging queue, and prompt/heuristic mapper are covered by the four files listed
above. The full test list is in the repository root `README.md`.
