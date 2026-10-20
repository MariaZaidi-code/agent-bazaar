# Agent Message Protocol

All agent messages are Pydantic models in `app/schemas.py`. They share an envelope and are persisted by `MessageBus` into the `messages` table in `data/runtime/traces.db`. The UI can retrieve them at `GET /api/tasks/{task_id}/messages`.

## Envelope

```json
{
  "message_id": "msg_01J...",
  "timestamp": "2026-10-20T12:00:00Z",
  "sender": "client",
  "recipient": "interface",
  "correlation_id": "task_abc123",
  "kind": "CandidateList"
}
```

| Field | Meaning |
|---|---|
| `message_id` | Unique message identifier |
| `timestamp` | UTC creation time |
| `sender` | Emitting agent role |
| `recipient` | Intended consumer, when known |
| `correlation_id` | Task or request correlation identifier |
| `kind` | Discriminator used by subscribers |

## Message families

### Task and discovery

| Kind | Direction | Key payload |
|---|---|---|
| `TaskRequest` | Interface -> Client | `task_id`, `task` |
| `CandidateList` | Client -> Interface/Auditor | `task_id`, `subgoal_id`, `capability`, `candidates[]` |
| `VerifyRequest` | Client -> Auditor | candidate list and sub-goal context |
| `VerifyResult` | Auditor -> Client | per-tool claim labels, overall labels, drift alerts |

`Candidate` includes the full `ToolSpec`, relevance, trust, score, rank, reasons, overall claim label, breaker state, demotion flag and eligibility.

### Execution

| Kind | Direction | Key payload |
|---|---|---|
| `ServiceOffer` | Provider -> Client | `provider_id`, `tool_id`, `capability`, price, claims |
| `ServiceCall` | Client -> Provider | `task_id`, `step_id`, `tool_id`, `params` |
| `ServiceResult` | Provider -> Client | status, data, error, latency, cache flag, source |
| `Feedback` | Client -> Trust | tool outcome, schema validity, optional rating |
| `TrustUpdate` | Client -> Trust/Interface | provider, signal, success, weight, reason |
| `SubstituteRequest` | Client -> Graph/Client | failed tool, capability, chosen substitute, reason |

`ServiceResult.status` is `success` or `error`. `source` distinguishes `live`, `fixture`, `mock`, filter sources and cache reuse.

### Safety and repair

| Kind | Direction | Key payload |
|---|---|---|
| `DriftAlert` | Auditor -> Client/Interface | tool, provider, severity, reasons |
| `ListingSubmit` | Mapper/Interface -> Knowledge | name, description, capability, typed inputs/outputs, claims |
| `CorrectionSubmit` | Interface -> Mapper | tool, field, original concept, corrected concept/unit, note |
| `MapResult` | Mapper -> Knowledge/Interface | mapped inputs/outputs, violations, accepted, staged |
| `RepairRequest` | Knowledge -> Mapper | tool, violations, attempt number |

## Example: candidate list

```json
{
  "kind": "CandidateList",
  "sender": "client",
  "recipient": "interface",
  "correlation_id": "task_abc123",
  "task_id": "task_abc123",
  "subgoal_id": "g2",
  "capability": "GetWeatherForecast",
  "candidates": [
    {
      "tool": {"id": "open-meteo-forecast", "provider_id": "open-meteo"},
      "relevance": 0.91,
      "trust": 0.62,
      "score": 0.5642,
      "rank": 1,
      "reasons": ["lexical similarity 0.68", "trust 0.62", "claim label Verified"],
      "claim_label": "Verified",
      "breaker_state": "closed",
      "demoted": false,
      "eligible": true
    }
  ]
}
```

## Example: trust update

```json
{
  "kind": "TrustUpdate",
  "sender": "client",
  "recipient": "trust",
  "correlation_id": "task_abc123",
  "provider_id": "open-meteo-backup",
  "signal": "call",
  "success": true,
  "reason": "substitute completed schema-valid call",
  "source": "execution"
}
```

## Trace events

A trace event is not a message; it is a durable decision record:

```json
{
  "task_id": "task_abc123",
  "seq": 14,
  "timestamp": "2026-10-20T12:00:01Z",
  "event_type": "substitution_succeeded",
  "actor": "client",
  "summary": "Chain recovered with substitute open-meteo-forecast-backup.",
  "data": {
    "failed_tool": "open-meteo-forecast",
    "substitute": "open-meteo-forecast-backup"
  }
}
```

Important event types:

- `task_started`, `task_decomposed`
- `graphrag_shortlist`, `claims_verified`, `candidate_ranking`
- `planning_finished`, `chain_composed`
- `step_started`, `step_succeeded`, `step_failed`
- `substitution_requested`, `substitute_selected`, `substitution_succeeded`
- `link_rejected`, `breaker_changed`, `trust_updated`
- `task_completed`, `task_partial`, `task_failed`

## Compatibility rules

- Unknown fields are ignored by Pydantic by default; new optional fields are backward compatible.
- `kind` is the discriminator used by `MessageBus` subscribers. External Mapper/Auditor implementations must preserve the existing `kind` values or register new subscribers.
- Claim labels use the enum values `Verified`, `Supported`, `Unsupported`, `Contradicted`.
- Step statuses are `pending`, `completed`, `failed`, `substituted`, `skipped`.
- Task statuses are `completed`, `partial`, `failed`.

## Integration notes

The Client does not import a concrete external Auditor or Mapper. It consumes the adapter methods in `app/agents/auditor_stub.py` and `app/agents/mapper_stub.py`. Replacing those adapters with a real message bus transport is a matter of forwarding the same Pydantic payloads and preserving the correlation ID.
