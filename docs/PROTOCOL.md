# Protocol and Message Contracts

The Auditor exposes Python message types, JSON serializations of those types, a local HTTP API, and two outbound integrations: a trust registry webhook and persisted artifact logs. All JSON uses `snake_case`. Timestamps are ISO 8601 in UTC. IDs are opaque strings.

## Message envelope

Every message inherits these fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `sender` | string | Producing component. Auditor messages use `auditor`. |
| `correlation_id` | string | Ties a request, probe, result, alert, and trust update together. |
| `id` | string | Unique message id. |
| `timestamp` | string | Creation time. |
| `type` | string | Runtime type name; added during serialization. |

Serialization is `Message.to_dict()` / `to_json()`. Enums serialize to their string values, nested dataclasses serialize recursively, and lists/objects are preserved.

## VerifyRequest

Python: `agent_bazaar_auditor.messages.VerifyRequest`

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `tool_id` | string | required | Catalog key. |
| `claims` | array or null | null | Optional explicit claims. |
| `request_all_claims` | boolean | true | If true, use all catalog claims. |
| `reprobe_round` | integer | 0 | Monitoring round. |

```json
{
  "sender": "client",
  "correlation_id": "req-42",
  "id": "req-42",
  "timestamp": "2026-10-24T22:00:00+00:00",
  "tool_id": "open-meteo",
  "claims": null,
  "request_all_claims": true,
  "reprobe_round": 0,
  "type": "VerifyRequest"
}
```

A `VerifyRequest` without `claims` and with `request_all_claims=true` verifies the catalog claim set. A caller-supplied claim must have a matching `tool_id`; otherwise the Auditor rejects the request.

## Claim

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Stable claim id. |
| `tool_id` | string | Owning tool. |
| `text` | string | Human-readable assertion. |
| `claim_type` | enum string | `output_field`, `unit`, `authentication`, `limit`, `availability`, `behaviour`. |
| `field_path` | string or null | Dotted response path. |
| `expected_type` | string or null | `string`, `number`, `array`, `object`, `boolean`, `present`, `any`, `xml`. |
| `expected_unit` | string or null | Expected unit, such as `celsius`. |
| `expected_min`, `expected_max` | number or null | Plausible numeric bounds. |
| `expected_limit` | number or null | Documented limit, where probeable. |
| `probeable` | boolean | Whether the probe can produce evidence. |
| `source_text` | string | Documentation sentence used to derive the claim. |
| `ground_truth_label` | string or null | Evaluation-only label. |
| `metadata` | object | Claim-specific hints, such as `expects_key`. |

```json
{
  "id": "95df0a5191ee",
  "tool_id": "ipify",
  "text": "Returns the public IP address.",
  "claim_type": "output_field",
  "field_path": "ip",
  "expected_type": "string",
  "expected_unit": null,
  "expected_min": null,
  "expected_max": null,
  "expected_limit": null,
  "probeable": true,
  "source_text": "Returns the public IP address.",
  "ground_truth_label": null,
  "metadata": {}
}
```

`ground_truth_label` is not used by the decision logic. It exists only in frozen evaluation data.

## Evidence

| Field | Type | Meaning |
| --- | --- | --- |
| `id` | string | Evidence id. |
| `claim_id` | string | Claim it supports. |
| `kind` | string | `document` or `probe`. |
| `source` | string | Documentation chunk or probe artifact reference. |
| `summary` | string | Short finding. |
| `quote` | string | Documentation text or joined probe checks. |
| `doc_stance` | string or null | `supports`, `contradicts`, `silent`. |
| `probe_outcome` | string or null | `agrees`, `disagrees`, `not_probeable`, `not_probed`, `probe_error`. |
| `created_at` | string | Creation time. |
| `metadata` | object | Probe status, URL, raw response excerpt, retrieval details. |

Evidence lists contain both documentation and probe evidence when both are available. `raw_response` is truncated to avoid unbounded payload storage.

## ClaimAssessment

| Field | Type | Meaning |
| --- | --- | --- |
| `claim` | object | Serialized `Claim`. |
| `label` | enum string | `Verified`, `Supported`, `Contradicted`, `Unsupported`. |
| `doc_stance` | enum string | `supports`, `contradicts`, `silent`. |
| `probe_outcome` | enum string | Probe result for this claim. |
| `evidence` | array | Document and probe evidence. |
| `rationale` | string | Decision narrative. |
| `probe_source` | string | `live`, `cache`, `fixture`, `mock`, `manual`, or empty. |
| `probed` | boolean | Whether usable probe evidence was produced. |
| `probe_error` | string | Transport or parsing error, if any. |
| `probe_status_code` | integer or null | HTTP status. |
| `probe_latency_ms` | number or null | Probe latency. |
| `probe_artifact` | string | Relative artifact path. |
| `probe_checks` | array of strings | Human-readable checks that ran. |

The label is produced only by `decision.decide_label`. Consumers should not re-derive labels from `doc_stance` and `probe_outcome` because policy changes belong in one place.

## CoverageReport

| Field | Type | Meaning |
| --- | --- | --- |
| `total_claims` | integer | Requested claims. |
| `probeable_claims` | integer | Claims whose type supports probing. |
| `probed_claims` | integer | Claims with usable probe evidence. |
| `coverage_percent` | number | `probed / total * 100`. |
| `probeable_coverage_percent` | number | `probed / probeable * 100`. |
| `per_tool` | object | Tool to coverage percentage. |
| `probe_sources` | object | Evidence source to claim count. |
| `notes` | array of strings | Coverage caveats. |

Coverage is not a confidence score. It reports how much of the claim set has probe evidence and why the rest does not.

## VerifyResult

| Field | Type | Meaning |
| --- | --- | --- |
| `request_id` | string | `id` of the originating request. |
| `tool_id` | string | Tool verified. |
| `assessments` | array | One `ClaimAssessment` per claim. |
| `coverage` | object | `CoverageReport`. |
| `started_at`, `finished_at` | string | Timing bounds. |
| `duration_ms` | number | Wall-clock duration. |
| `probe_source` | string | Source of the shared probe. |
| `notes` | array of strings | Human-readable caveats. |
| `probe_artifact` | string | Persisted probe path. |
| `probe_status_code` | integer or null | Shared probe status. |
| `probe_latency_ms` | number or null | Shared probe latency. |
| `probe_valid` | boolean or null | Whether schema validation passed. |
| `drift_alerts` | array | `DriftAlert` objects from this round. |

Abridged example:

```json
{
  "sender": "auditor",
  "correlation_id": "req-42",
  "id": "res-42",
  "timestamp": "2026-10-24T22:00:00.005+00:00",
  "request_id": "req-42",
  "tool_id": "ipify",
  "assessments": [
    {
      "claim": {"id": "95df0a5191ee", "tool_id": "ipify", "text": "Returns the public IP address."},
      "label": "Verified",
      "doc_stance": "supports",
      "probe_outcome": "agrees",
      "evidence": [],
      "rationale": "documentation supports the claim; the probe agrees; decision table returns Verified.",
      "probe_source": "fixture",
      "probed": true,
      "probe_error": "",
      "probe_status_code": 200,
      "probe_latency_ms": 0.0,
      "probe_artifact": "probes/ipify/2026-10-24T22-00-00_00-00.json",
      "probe_checks": ["field ip is present", "field ip has type string"]
    }
  ],
  "coverage": {
    "total_claims": 2,
    "probeable_claims": 2,
    "probed_claims": 2,
    "coverage_percent": 100.0,
    "probeable_coverage_percent": 100.0,
    "per_tool": {"ipify": 100.0},
    "probe_sources": {"fixture": 2},
    "notes": []
  },
  "started_at": "2026-10-24T22:00:00+00:00",
  "finished_at": "2026-10-24T22:00:00.005+00:00",
  "duration_ms": 4.878,
  "probe_source": "fixture",
  "notes": [],
  "probe_artifact": "probes/ipify/2026-10-24T22-00-00_00-00.json",
  "probe_status_code": 200,
  "probe_latency_ms": 0.0,
  "probe_valid": true,
  "drift_alerts": [],
  "type": "VerifyResult"
}
```

The example is abbreviated; real assessments include full evidence objects.

## DriftAlert

| Field | Type | Meaning |
| --- | --- | --- |
| `tool_id` | string | Tool that drifted. |
| `field_path` | string | Dotted path, or empty for transport-level alerts. |
| `detector` | enum string | `rule` or `embedding`. |
| `old_description` | string | Expected contract at the path. |
| `new_sample` | any | Observed value or schema excerpt. Truncated when large. |
| `severity` | enum string | `low`, `medium`, `high`, `critical`. |
| `distance` | number or null | Embedding cosine distance when applicable. |
| `probe_round` | integer | Monitoring round. |
| `details` | object | Finding kind, message, and detector-specific fields. |

```json
{
  "sender": "auditor",
  "correlation_id": "req-42",
  "id": "alert-1",
  "timestamp": "2026-10-24T22:00:01+00:00",
  "tool_id": "open-meteo",
  "field_path": "current.temperature_2m",
  "detector": "rule",
  "old_description": "current.temperature_2m: number, unit celsius, range [-90, 60]",
  "new_sample": "77.0",
  "severity": "medium",
  "distance": null,
  "probe_round": 1,
  "details": {
    "kind": "out_of_range",
    "message": "Value at current.temperature_2m is above the mapped plausible range."
  },
  "type": "DriftAlert"
}
```

Common `details.kind` values include:

- `renamed_field` with `candidate_path`;
- `missing_field`;
- `type_changed`;
- `unit_changed` with `unit_path` and `observed_unit`;
- `out_of_range`;
- `new_required_parameter`;
- `transport`;
- embedding kinds with threshold and schema-summary details.

For a rename, the Mapper can use `field_path` as the old path and `details.candidate_path` as the proposed new path. The Auditor does not apply that change.

## TrustUpdate

| Field | Type | Meaning |
| --- | --- | --- |
| `tool_id` | string | Tool being scored. |
| `outcome` | enum string | Audit outcome. |
| `reason` | string | Human-readable justification. |
| `claim_id` | string | Related claim, or empty. |
| `value` | number or null | Optional value, such as alert distance. |

Outcome values:

| Outcome | Treated as |
| --- | --- |
| `probe_pass` | success |
| `schema_valid` | success |
| `call_success` | success |
| `probe_fail` | failure |
| `schema_invalid` | failure |
| `call_failure` | failure |
| `contradiction` | failure |
| `drift` | failure |
| `rating` | success if `value >= 0.5`; otherwise failure |

```json
{
  "sender": "auditor",
  "correlation_id": "req-42",
  "id": "trust-1",
  "timestamp": "2026-10-24T22:00:01+00:00",
  "tool_id": "open-meteo",
  "outcome": "contradiction",
  "reason": "documentation supports the claim; the probe disagrees; decision table returns Contradicted.",
  "claim_id": "61759eb13ddc",
  "value": 0.0,
  "type": "TrustUpdate"
}
```

### Delivery contract

When `ABA_TRUST_REGISTRY_URL` is set, the Auditor sends each update as:

```http
POST <ABA_TRUST_REGISTRY_URL>
Content-Type: application/json
User-Agent: agent-bazaar-auditor/1.0
```

A `2xx` response means delivered. Any transport error or non-2xx response is counted in `delivery_failures`; the local ledger and log still receive the update. Delivery is best effort and does not block verification.

## Feedback, CorrectionSubmit, RepairRequest

These contracts are defined for the wider Agent Bazaar loop. They are not emitted by the default verification pipeline.

```json
{
  "sender": "client",
  "tool_id": "open-meteo",
  "outcome": "wrong_unit",
  "rating": 0.0,
  "details": {"observed_unit": "fahrenheit"},
  "type": "Feedback"
}
```

```json
{
  "sender": "client",
  "tool_id": "open-meteo",
  "field_path": "current.temperature_2m",
  "proposed_concept": "temperature",
  "proposed_unit": "celsius",
  "note": "Response is in Fahrenheit.",
  "type": "CorrectionSubmit"
}
```

```json
{
  "sender": "auditor",
  "tool_id": "open-meteo",
  "violations": ["unit_changed:current.temperature_2m"],
  "attempt": 1,
  "type": "RepairRequest"
}
```

## HTTP API

The server binds to `127.0.0.1:8765` by default. It has no authentication. Use it for local integration and demos, not as a public service.

### GET endpoints

| Path | Response |
| --- | --- |
| `/health` | `status`, `version`, `offline_fixtures`, `tools`, `probe_definitions`, `baselines`, `trust_observations`. |
| `/tools` | `tools`: tool id, name, category, claim count, probeability. |
| `/probes` | `probes`: serialized probe definitions, including safe input. |
| `/trust` | `leaderboard`: trust rows; `feed`: update counts and delivery failures. |

### POST endpoints

`/verify`:

```json
{
  "tool_id": "open-meteo",
  "claims": null,
  "correlation_id": "client-1",
  "force_live": false,
  "round": 0,
  "establish_baseline": true
}
```

Response: `{"result": <VerifyResult>}`.

`/monitor` accepts the same body plus `round` and `establish_baseline` (default false). Response: `{"result": <VerifyResult>}` with `drift_alerts`.

`/probe`:

```json
{"tool_id": "ipify", "force_live": false}
```

Response: `{"probe": <ProbeResult>}`.

`/mock` is available only when the server is started with `--mock`:

```json
{"tool_id": "open-meteo", "behavior": "dishonest", "options": {}}
```

Response: `{"mock": <provider state>}`. Behavior values match `MockBehavior`.

Errors use `{"error": "..."}` with HTTP 400 for bad input, 404 for unknown paths, 501 for disabled mock control, and 500 for unexpected failures.

## Persistence contracts

When persistence is enabled, the artifact store writes:

- `messages.jsonl`: every request and result envelope;
- `probe_index.jsonl`: one row per probe with artifact path and correlation id;
- `knowledge.jsonl`: assessments for downstream knowledge integration;
- `graph_writes.jsonl`: claim-evidence graph rows;
- `drift_alerts.jsonl`: every serialized `DriftAlert`;
- `trust_updates.jsonl`: every serialized `TrustUpdate`;
- `baselines.json`: per-tool schema embeddings;
- `trust_ledger.json`: local Beta ledger;
- `probes/`, `verifications/`, and `reports/`: full JSON artifacts.

JSONL rows are append-only. JSON state files are written atomically by `utils.atomic_write_json`.

## Compatibility rules

- Additive fields are safe; consumers should ignore unknown keys.
- Enum values are part of the contract. Do not rename them without a migration.
- `type` is informational for routing, not a replacement for endpoint semantics.
- `ground_truth_label` must never influence runtime labels.
- Consumers must treat `Supported` as evidence-limited, not as a synonym for `Verified`.
