# Evaluation

This is the evaluation snapshot for the standalone Auditor. It covers claim verification, drift detection with and without embeddings, false alarms, and the dishonest-provider trust experiment.

The results are reproduced by:

```powershell
agent-bazaar-auditor evaluate
```

The command writes `outputs/reports/evaluation_summary.json` and `.md`, plus one JSON and Markdown report per area. The datasets are frozen in `data/` so another baseline can be scored on the same items.

## Headline results

| Area | Result |
| --- | --- |
| Claim verification | 60/60 correct; accuracy 1.000; macro F1 1.000 |
| Claim coverage | 46/60 probed; 76.67% overall; 100% of probeable claims |
| Drift, rule-only | 34/40 detected; 34/40 correct detector |
| Drift, rules + embedding | 40/40 detected; 40/40 correct detector |
| False alarms | 0/30 known-good variations in both modes |
| Trust experiment | 5/5 bad providers demoted; 0/5 honest providers demoted |
| Trust precision / recall | 1.000 / 1.000 |
| Mean rounds to demotion | 1.60 |

These are controlled results. They are a regression benchmark and a detector check, not an estimate of how often real providers lie.

## Claim verification

### Dataset

The frozen set contains 105 claims:

| Label | Count | Origin |
| --- | ---: | --- |
| Verified | 62 | Real documentation claims plus seeded variants |
| Supported | 13 | Real documentation claims that cannot be fully probed |
| Contradicted | 15 | Seeded false claims |
| Unsupported | 15 | Seeded claims with no supporting evidence |

Seeded contradictions include wrong units, wrong limits, wrong types, false authentication claims, and missing fields. Real claims are derived from the tool documentation shipped in `tools.py`.

### Method

For each tool, the evaluation uses one shared probe and assesses every claim against that probe plus retrieved documentation. The label comes from the fixed decision table. The deterministic judge is used; no LLM is required. Probe responses come from the controlled mock/fixture layer so the run is offline and repeatable.

### Confusion matrix

| Expected \ Predicted | Verified | Supported | Contradicted | Unsupported |
| --- | ---: | ---: | ---: | ---: |
| Verified | 62 | 0 | 0 | 0 |
| Supported | 0 | 13 | 0 | 0 |
| Contradicted | 0 | 0 | 15 | 0 |
| Unsupported | 0 | 0 | 0 | 15 |

### Per-label metrics

| Label | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Verified | 1.000 | 1.000 | 1.000 | 62 |
| Supported | 1.000 | 1.000 | 1.000 | 13 |
| Contradicted | 1.000 | 1.000 | 1.000 | 15 |
| Unsupported | 1.000 | 1.000 | 1.000 | 15 |

Accuracy is 1.000 (105/105). Macro F1 is 1.000.

The report also splits real and seeded subsets. Each subset omits at least one label, so a per-subset macro F1 is not comparable to the overall four-label macro F1. Accuracy on both subsets is 1.000.

### Coverage

| Measure | Value |
| --- | ---: |
| Total claims | 105 |
| Probeable claims | 82 |
| Probed claims | 82 |
| Coverage of all claims | 78.10% |
| Coverage of probeable claims | 100.00% |

Coverage is reported even when it is below 100%. The 23 non-probed claims are documentation-backed or evidence-limited claims, not failed probes. A `Supported` label is the honest result when documentation supports a claim but the runtime cannot fully test it.

### Cost

| Measure | Offline result |
| --- | ---: |
| Mean time per claim (probe + assess) | approximately 0.6 ms |
| p95 time per claim | approximately 1.2 ms |
| LLM tokens | 0 in deterministic mode |

These timings are from one local run and vary with machine load. Latency is dominated by local fixture processing. Live HTTP latency and token use depend on providers and the optional LLM judge; they are not extrapolated from this run.

## Drift detection

### Dataset and method

`data/drift_scenarios.json` contains 40 injected changes:

| Behaviour | Scenarios | What changes |
| --- | ---: | --- |
| Rename field | 8 | A mapped field is renamed, with a candidate replacement. |
| Remove field | 7 | A mapped field disappears. |
| Type change | 5 | A field changes JSON type. |
| Unit change | 2 | A value changes unit, such as Celsius to Fahrenheit. |
| Garbage 200 | 6 | HTTP 200 with polluted or meaningless content. |
| Outage | 5 | HTTP 5xx or transport failure. |
| Flapping | 5 | Provider alternates between working and failing. |
| Dishonest | 2 | Provider claims correctness while behaving badly. |

The first verification establishes a baseline. Each scenario is then re-probed and checked. Rule-only mode disables the embedding detector; full mode runs both.

### Threshold

Known-good variations test ordinary input differences: two variations per selected tool, 30 total.

| Measure | Value |
| --- | ---: |
| Known-good variations | 30 |
| Maximum known-good distance | 0.2021 |
| Mean known-good distance | 0.0373 |
| Tuned threshold | 0.252 |
| Rule | max known-good distance + 0.05 margin, never below 0.15 |

The threshold is stored in evaluation output, not hidden in a detector default.

### Rule-only versus full

| Mode | Detected | Detection rate | Correct detector | Mean rounds | False alarms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Rule-only | 34/40 | 0.850 | 34/40 | 1.15 | 0/30 |
| Rule + embedding | 40/40 | 1.000 | 40/40 | 1.12 | 0/30 |

### Detection by behaviour

| Behaviour | Scenarios | Detected, full | Correct detector | Detection rate |
| --- | ---: | ---: | ---: | ---: |
| Rename field | 8 | 8 | 8 | 1.000 |
| Remove field | 7 | 7 | 7 | 1.000 |
| Type change | 5 | 5 | 5 | 1.000 |
| Unit change | 2 | 2 | 2 | 1.000 |
| Garbage 200 | 6 | 6 | 6 | 1.000 |
| Outage | 5 | 5 | 5 | 1.000 |
| Flapping | 5 | 5 | 5 | 1.000 |
| Dishonest | 2 | 2 | 2 | 1.000 |

### Scenario detail

The generated report contains the full 40-row scenario table, including the tool,
behaviour, expected detector, detection round, distance and false-alarm state. See
`outputs/reports/drift_evaluation.md`; the aggregate results above are the stable
numbers to quote.

### Ablation interpretation

The six garbage-200 scenarios are the deliberate ablation target. The HTTP response is `200`, the mapped fields and types survive, and a rule-only check sees nothing wrong. The schema summary changes, so the embedding distance exceeds the threshold.

Rule-only mode detects 34/40 and misses exactly those six garbage-200 cases. Full mode detects 40/40. Both modes produce zero false alarms on the 30 known-good variations. That is the evidence that the embedding detector adds value rather than only adding noise on this set.

Flapping requires two rounds because the mock alternates states. That is why the full mean is 1.12 rather than exactly 1.0.

## Trust experiment

### Setup

Five honest and five bad providers are probed for up to eight rounds. The local Beta ledger records `probe_pass`, `probe_fail`, `schema_invalid`, `drift`, and `contradiction` outcomes. A provider is demoted when its score falls below 0.40.

The experiment measures the Auditor's TrustUpdate feed and ledger. It does not measure the Client's substitution policy or the production registry's weighting.

### Detection summary

| Metric | Value |
| --- | ---: |
| Honest providers | 5 |
| Bad providers | 5 |
| Bad providers demoted | 5 |
| Honest providers incorrectly demoted | 0 |
| Detection precision | 1.000 |
| Detection recall | 1.000 |
| Mean rounds until demotion | 1.60 |

### Trajectories

| Provider | Tool | Class | Demoted | Round | Final trust |
| --- | --- | --- | --- | ---: | ---: |
| frankfurter-honest | frankfurter | honest | no | - | 0.900 |
| nominatim-honest | nominatim | honest | no | - | 0.900 |
| restcountries-honest | rest-countries | honest | no | - | 0.900 |
| nager-honest | nager-date | honest | no | - | 0.900 |
| dogceo-honest | dog-ceo | honest | no | - | 0.900 |
| openmeteo-dishonest | open-meteo | bad | yes | 1 | 0.100 |
| ipify-outage | ipify | bad | yes | 1 | 0.100 |
| joke-flapping | joke-api | bad | yes | 4 | 0.300 |
| catfact-typechange | cat-fact | bad | yes | 1 | 0.100 |
| usgs-removefield | usgs-earthquake | bad | yes | 1 | 0.100 |

The bad-provider mean is 1.60 because the flapping provider takes four rounds. A single failure does not dominate the Beta score; repeated failures do.

## Baselines and ablations

- The Auditor and drift monitor contribute labels and alerts. Removing them leaves an unverified tool call with no structured evidence.
- Rule-only is the measured no-embedding ablation above.
- `data/seeded_claims.json` and `data/drift_scenarios.json` are the shared scoring sets for B1 (plain LLM tool calling) and B2 (RAG only).
- B1/B2 implementations and no-Auditor/no-drift scoring are external to this repository. The datasets are ready; the baseline runners are not included.
- Re-mapping accuracy is a Mapper metric. The Auditor supplies `old_description`, `new_sample`, and `details.candidate_path` for that loop.

## Interpretation

The claim set exercises all four labels and several subtle contradiction types. A perfect score shows that the decision procedure matches the curated ground truth and that the code did not regress. It does not show that a heuristic judge will be perfect on new provider documentation.

The drift set is deliberately controlled. Real keyless APIs rarely change inside a ten-week project, so injected changes are the only way to measure detector sensitivity. The 30 known-good variations are a small false-alarm sample; real baseline collection should continue across days and inputs.

The trust experiment uses a simple Beta ledger. Production trust may weight probe, schema, contradiction, rating, and drift outcomes differently. The contract is designed for that substitution.

## What is not measured

- Real-world prevalence of false claims.
- Human agreement or Cohen's kappa on labels.
- Re-mapping accuracy.
- Client substitution quality or circuit-breaker behavior.
- Production registry weighting.
- Long-window drift frequency.
- LLM judge accuracy on this set; the deterministic judge is used for the reported run.
- Live-provider latency and token cost.

## Reproducing artifacts

```powershell
agent-bazaar-auditor evaluate
```

Generated files:

```text
outputs/reports/
├── claim_evaluation.json
├── claim_evaluation.md
├── drift_evaluation.json
├── drift_evaluation.md
├── trust_evaluation.json
├── trust_evaluation.md
├── evaluation_summary.json
└── evaluation_summary.md
```

The `outputs/` directory is intentionally gitignored except for `.gitkeep`. This document is the committed snapshot of the latest controlled run.
