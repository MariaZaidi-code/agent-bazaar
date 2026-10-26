# Demo Guide

The demo is designed for a short live presentation and for repeatable screenshots. It runs entirely offline, takes a few seconds, and does not write into the repository.

## One-command demo

```powershell
agent-bazaar-auditor demo
```

If the console entry point is not installed:

```powershell
python -m agent_bazaar_auditor demo
```

The demo uses a temporary output directory and `persist=False`, so it does not contaminate `outputs/` or the evaluation baselines.

## What the audience sees

### 1. Healthy provider

Frankfurter returns the expected JSON, has no key requirement, and its documentation claims are consistent with the response.

Expected pattern:

```text
1. Healthy provider: Frankfurter
Tool: frankfurter
Probe: fixture HTTP 200 valid=True
Coverage: 66.67% overall, 100.00% of probeable claims
Labels: Verified=2, Supported=1
Drift alerts: 0
```

Talking point: `Supported` is not a failure. It is the honest label for a documentation claim that cannot be fully tested by a probe, such as a weekday-only update schedule.

### 2. Dishonest provider

Open-Meteo first establishes a healthy Celsius baseline. The mock then switches the unit to Fahrenheit without changing its documentation.

Expected pattern:

```text
2. Dishonest provider: Open-Meteo silently switches Celsius to Fahrenheit
Healthy baseline labels: ['Verified']
After injection: labels=['Contradicted', 'Verified'] alerts=2
  [medium] rule current.temperature_2m: Value at ... is above the mapped plausible range.
  [high] rule current.temperature_2m: Unit at current_units.temperature_2m is °F, expected celsius.
```

Talking points:

- The claim becomes `Contradicted` because the probe disagrees with the documented unit.
- Both an out-of-range rule and a unit rule fire.
- The alert carries the old description, new sample, field path, detector, and severity.
- The Mapper can use the alert to propose a new concept or unit; the Client can decide whether to substitute.

### 3. Outage

IPify returns HTTP 503.

Expected pattern:

```text
3. Outage: IPify returns HTTP 503
Labels=['Supported'] alerts=1
```

Talking point: an outage is not evidence that the documentation is false. The probe failed, so the label is `Supported`, and the transport alert still tells the client about availability.

### 4. Garbage 200

Nominatim returns HTTP 200 with a polluted schema.

Expected pattern:

```text
4. Garbage 200: Nominatim returns polluted schema
Detectors=['embedding'] alerts=1
  [high] embedding distance=0.386253: schema distance 0.3863 exceeds threshold 0.15
```

Talking point: this is the ablation case. The status is 200 and the expected mapped fields/types may still be present, so rules miss it. The schema embedding distance exceeds the tuned threshold.

The threshold in the demo is the default `0.15`. The evaluation tunes 0.252 from known-good variations and reports it in the evaluation output.

### 5. Trust leaderboard

Expected pattern:

```text
5. Trust leaderboard after observations
  frankfurter          score=0.750 observations=2 failures=0.0
  nominatim            score=0.714 observations=5 failures=1.0
  ipify                score=0.500 observations=4 failures=2.0
  open-meteo           score=0.444 observations=7 failures=4.0
```

Scores depend on the demo sequence, so the exact numbers may change if the demo is edited. The ordering and the direction of movement are the point: healthy providers stay high, injected failures push scores down.

## Optional live-provider demo

Live probes require network access and may be rate-limited. Use one small tool first:

```powershell
agent-bazaar-auditor probe ipify --live
agent-bazaar-auditor verify frankfurter --live --no-persist
```

Then show the same evaluation logic with a tool that has more claims:

```powershell
agent-bazaar-auditor verify open-meteo --live --no-persist
```

If a provider is down, the output should say so and the decision table should avoid `Verified`. That is the intended behavior, not a demo failure.

## Optional API demo

Start the server with mock control:

```powershell
agent-bazaar-auditor serve --mock
```

In another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/health
Invoke-RestMethod http://127.0.0.1:8765/tools

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/verify `
  -ContentType "application/json" `
  -Body '{"tool_id":"frankfurter"}'

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/mock `
  -ContentType "application/json" `
  -Body '{"tool_id":"open-meteo","behavior":"dishonest"}'

Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/monitor `
  -ContentType "application/json" `
  -Body '{"tool_id":"open-meteo","round":1,"establish_baseline":false}'
```

Use `--mock` only on a local, trusted machine. The API has no authentication.

## Manual mock control from Python

```python
from agent_bazaar_auditor.auditor import Auditor
from agent_bazaar_auditor.mocks.registry import MockRegistry

auditor = Auditor(persist=False)
registry = MockRegistry(auditor.harness, catalog=auditor.catalog, definitions=auditor.definitions)

auditor.verify("open-meteo", establish_baseline=True)
registry.control("open-meteo", "dishonest")
result = auditor.monitor_tool("open-meteo", probe_round=1, establish_baseline=False)

for alert in result.drift_alerts:
    print(alert.detector.value, alert.field_path, alert.details.get("kind"))
```

Available behaviours are listed in `MockBehavior`:

```text
normal
rename_field
unit_change
type_change
remove_field
garbage_200
exaggerated_claim
outage
flapping
dishonest
```

## Demo narrative

A concise spoken track:

> The Auditor does not trust documentation or a single successful call. It extracts testable claims, retrieves the documentation evidence, probes the tool once with a safe input, and applies a fixed decision table. A healthy call produces Verified; an untestable documentation claim produces Supported. When the provider changes Celsius to Fahrenheit, the probe contradicts the claim, the field rule fires, and the claim becomes Contradicted. The DriftAlert carries enough information for the Mapper to propose a corrected field and for the Client to lower trust. An outage is treated as missing evidence, not as a lie. A garbage 200 response is missed by simple rules, which is why we also compare the response schema embedding with a tuned baseline.

## What to show if there is only one minute

Run:

```powershell
agent-bazaar-auditor demo
```

Point at four lines:

1. Frankfurter has zero drift alerts.
2. Open-Meteo becomes `Contradicted` after the unit switch.
3. IPify stays `Supported` during an outage.
4. Nominatim is caught by the embedding detector, not the rule detector.

Then show the headline evaluation table in `docs/EVALUATION.md`.

## Troubleshooting

- **Command not found:** use `python -m agent_bazaar_auditor demo` from the repository root after `pip install -e .`.
- **PowerShell activation blocked:** run `Set-ExecutionPolicy -Scope Process Bypass`, then activate again.
- **Live probe fails:** this is expected on rate limits or outages; use the offline demo for the recorded presentation.
- **Mock controls do nothing:** start the API with `--mock`, and use `establish_baseline=false` for monitor calls after establishing a baseline.
- **Garbled terminal symbols:** use Windows Terminal or the VS Code integrated terminal. The CLI emits UTF-8; older console code pages may render the degree symbol poorly.
