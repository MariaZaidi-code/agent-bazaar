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
| Drift, rule-only | 17/20 detected; 17/20 correct detector |
| Drift, rules + embedding | 20/20 detected; 20/20 correct detector |
| False alarms | 0/30 known-good variations in both modes |
| Trust experiment | 5/5 bad providers demoted; 0/5 honest providers demoted |
| Trust precision / recall | 1.000 / 1.000 |
| Mean rounds to demotion | 1.60 |

These are controlled results. They are a regression benchmark and a detector check, not an estimate of how often real providers lie.

## Claim verification

### Dataset

The frozen set contains 60 claims:

| Label | Count | Origin |
| --- | ---: | --- |
| Verified | 32 | Real documentation claims |
| Supported | 8 | Real documentation claims that cannot be fully probed |
| Contradicted | 10 | Seeded false claims |
| Unsupported | 10 | Seeded claims with no supporting evidence |

Seeded contradictions include wrong units, wrong limits, wrong types, false authentication claims, and missing fields. Real claims are derived from the tool documentation shipped in `tools.py`.

### Method

For each tool, the evaluation uses one shared probe and assesses every claim against that probe plus retrieved documentation. The label comes from the fixed decision table. The deterministic judge is used; no LLM is required. Probe responses come from the controlled mock/fixture layer so the run is offline and repeatable.

### Confusion matrix

| Expected \ Predicted | Verified | Supported | Contradicted | Unsupported |
| --- | ---: | ---: | ---: | ---: |
| Verified | 32 | 0 | 0 | 0 |
| Supported | 0 | 8 | 0 | 0 |
| Contradicted | 0 | 0 | 10 | 0 |
| Unsupported | 0 | 0 | 0 | 10 |

### Per-label metrics

| Label | Precision | Recall | F1 | Support |
| --- | ---: | ---: | ---: | ---: |
| Verified | 1.000 | 1.000 | 1.000 | 32 |
| Supported | 1.000 | 1.000 | 1.000 | 8 |
| Contradicted | 1.000 | 1.000 | 1.000 | 10 |
| Unsupported | 1.000 | 1.000 | 1.000 | 10 |

Accuracy is 1.000 (60/60). Macro F1 is 1.000.

The report also splits real and seeded subsets. Each subset omits at least one label, so a per-subset macro F1 is not comparable to the overall four-label macro F1. Accuracy on both subsets is 1.000.

### Coverage

| Measure | Value |
| --- | ---: |
| Total claims | 60 |
| Probeable claims | 46 |
| Probed claims | 46 |
| Coverage of all claims | 76.67% |
| Coverage of probeable claims | 100.00% |

Coverage is reported even when it is below 100%. The 14 non-probed claims are documentation-backed or evidence-limited claims, not failed probes. A `Supported` label is the honest result when documentation supports a claim but the runtime cannot fully test it.

### Cost

| Measure | Offline result |
| --- | ---: |
| Mean time per claim (probe + assess) | approximately 0.6 ms |
| p95 time per claim | approximately 1.2 ms |
| LLM tokens | 0 in deterministic mode |

These timings are from one local run and vary with machine load. Latency is dominated by local fixture processing. Live HTTP latency and token use depend on providers and the optional LLM judge; they are not extrapolated from this run.

## Drift detection

### Dataset and method

`data/drift_scenarios.json` contains 20 injected changes:

| Behaviour | Scenarios | What changes |
| --- | ---: | --- |
| Rename field | 4 | A mapped field is renamed, with a candidate replacement. |
| Remove field | 4 | A mapped field disappears. |
| Type change | 2 | A field changes JSON type. |
| Unit change | 2 | A value changes unit, such as Celsius to Fahrenheit. |
| Garbage 200 | 3 | HTTP 200 with polluted or meaningless content. |
| Outage | 2 | HTTP 5xx or transport failure. |
| Flapping | 2 | Provider alternates between working and failing. |
| Dishonest | 1 | Provider claims correctness while behaving badly. |

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
| Rule-only | 17/20 | 0.850 | 17/20 | 1.12 | 0/30 |
| Rule + embedding | 20/20 | 1.000 | 20/20 | 1.10 | 0/30 |

### Detection by behaviour

| Behaviour | Scenarios | Detected, full | Correct detector | Detection rate |
| --- | ---: | ---: | ---: | ---: |
| Rename field | 4 | 4 | 4 | 1.000 |
| Remove field | 4 | 4 | 4 | 1.000 |
| Type change | 2 | 2 | 2 | 1.000 |
| Unit change | 2 | 2 | 2 | 1.000 |
| Garbage 200 | 3 | 3 | 3 | 1.000 |
| Outage | 2 | 2 | 2 | 1.000 |
| Flapping | 2 | 2 | 2 | 1.000 |
| Dishonest | 1 | 1 | 1 | 1.000 |

### Scenario detail

| ID | Tool | Behaviour | Expected detector | Detected | Round | Distance |
| --- | --- | --- | --- | --- | ---: | ---: |
| drift-01 | open-meteo | rename_field | rule | yes | 1 | 0.0055 |
| drift-02 | rest-countries | rename_field | rule | yes | 1 | 0.0301 |
| drift-03 | usgs-earthquake | rename_field | rule | yes | 1 | 0.0190 |
| drift-04 | dog-ceo | rename_field | rule | yes | 1 | 0.1758 |
| drift-05 | nager-date | remove_field | rule | yes | 1 | 0.0373 |
| drift-06 | open-library | remove_field | rule | yes | 1 | 0.4132 |
| drift-07 | open-meteo | remove_field | rule | yes | 1 | 0.0050 |
| drift-08 | arxiv | remove_field | rule | yes | 1 | 0.0074 |
| drift-09 | cat-fact | type_change | rule | yes | 1 | 0.1433 |
| drift-10 | coingecko | type_change | rule | yes | 1 | 0.1928 |
| drift-11 | open-meteo | unit_change | rule | yes | 1 | 0.0000 |
| drift-12 | open-meteo | unit_change | rule | yes | 1 | 0.0000 |
| drift-13 | open-meteo | garbage_200 | embedding | yes | 1 | 0.2697 |
| drift-14 | nominatim | garbage_200 | embedding | yes | 1 | 0.3863 |
| drift-15 | rest-countries | garbage_200 | embedding | yes | 1 | 0.3021 |
| drift-16 | ipify | outage | rule | yes | 1 | - |
| drift-17 | worldtime | outage | rule | yes | 1 | - |
| drift-18 | joke-api | flapping | rule | yes | 2 | - |
| drift-19 | datamuse | flapping | rule | yes | 2 | - |
| drift-20 | open-meteo | dishonest | rule | yes | 1 | 0.0000 |

### Ablation interpretation

The three garbage-200 scenarios are the deliberate ablation target. The HTTP response is `200`, the mapped fields and types survive, and a rule-only check sees nothing wrong. The schema summary changes, so the embedding distance exceeds the threshold.

Rule-only mode detects 17/20 and misses exactly those three garbage-200 cases. Full mode detects 20/20. Both modes produce zero false alarms on the 30 known-good variations. That is the evidence that the embedding detector adds value rather than only adding noise on this set.

Flapping requires two rounds because the mock alternates states. That is why the full mean is 1.10 rather than exactly 1.0.

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
