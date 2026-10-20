# Evaluation Guide

## Purpose

The evaluation suite measures the Client side of Agent Bazaar against the work-plan requirements:

- tool discovery and GraphRAG ranking;
- traceable chain composition and execution;
- comparison against the B1 tool-calling and B2 RAG-only baselines;
- typed link validation;
- circuit-breaker substitution under provider failure;
- trust scoring, demotion and replay;
- ablations of ontology, Auditor, trust, feedback, substitution and breaker features.

All suites run offline against deterministic fixtures. This is deliberate: the evaluation is reproducible, needs no API keys, and isolates orchestration quality from internet variability. Live API behavior should be checked separately before a final demonstration.

## Run everything

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.run_all
```

Individual suites:

```powershell
.\.venv\Scripts\python.exe -m app.evaluation.run_matching
.\.venv\Scripts\python.exe -m app.evaluation.run_chains
.\.venv\Scripts\python.exe -m app.evaluation.run_baselines
.\.venv\Scripts\python.exe -m app.evaluation.run_substitution
.\.venv\Scripts\python.exe -m app.evaluation.run_trust
.\.venv\Scripts\python.exe -m app.evaluation.run_ablations
```

Outputs are written to `reports/*.json`. The API exposes them at `GET /api/evaluations`.

## Datasets

| File | Size | Content |
|---|---:|---|
| `app/evaluation/data/matching_tasks.json` | 50 tasks / 67 expected links | Single and multi-intent tasks across every seeded capability |
| `app/evaluation/data/chain_tasks.json` | 15 tasks | End-to-end chains with expected capabilities and tools |
| `app/evaluation/data/substitution_cases.json` | 7 cases | Six recoverable provider failures and one negative control with no substitute |
| `app/evaluation/data/trust_scenarios.json` | 6 scenarios | Success, outage, contradiction, mixed evidence, recovery and weak evidence |

Each matching entry maps a capability to its expected tool:

```json
{
  "id": "m01",
  "task": "What is the weather in Lahore tomorrow?",
  "expected": {
    "GeocodeLocation": "nominatim-geocode",
    "GetWeatherForecast": "open-meteo-forecast"
  }
}
```

## Metrics

### Matching

- **Capability coverage**: expected capability has a candidate list.
- **Hit@k**: expected tool appears anywhere in the returned shortlist.
- **Top-1 accuracy**: expected tool is ranked first.
- **MRR**: mean reciprocal rank of the expected tool.
- **Selected-tool accuracy**: the Client actually selected the expected tool for the sub-goal.
- **Task completion rate**: the full Client task completed, independent of ranking.
- **Per-capability breakdown** for diagnosis.

### Chains

- **Success rate**: status is completed, every expected tool ran, and no expected capability is missing.
- **Expected capability coverage**: fraction of expected links satisfied.
- **Answer rate**: non-empty synthesized answer.
- **Trace coverage**: at least one trace event.
- **Completion event rate**: `task_completed` recorded.
- **Average latency and steps**.

### Baselines

The full Client and both baselines run the same 15 chain tasks in fresh runtimes. A separate injected weather failure tests recovery.

- **Chain success rate**: tasks completed.
- **Expected tool selection accuracy**: top-ranked/selected tool matches the environment's expected primary tool for every expected capability.
- **Fault recovery**: after one primary weather failure, the run completes through the backup mirror. Baselines have no substitution layer and are expected to fail this case.
- **Delta**: full chain success minus the better baseline.

The curated chain set is intentionally within both baselines' competence, so normal success is equal. The fault case is the discriminator: the full Client recovers, while B1 and B2 return a partial result.

### Substitution

Each case is run in a fresh runtime with `breaker_failure_threshold=1`.

- **Recovery accuracy**: the expected recovery outcome occurred. Positive cases must recover through the named substitute; the negative control must not recover.
- **Substitute accuracy**: the recovered step used the expected mirror with `substituted_from` set to the failed tool.
- **Unexpected recovery rate**: a negative control recovered when it should not.
- **Trace coverage**: `substitution_succeeded` is present.
- **Average latency**.

### Trust

Scenarios apply weighted success, failure, schema, rating and contradiction signals to a fresh trust registry.

- **Pass rate**: all scenario checks hold.
- **Demotion accuracy**: expected demotion state matches observed state.
- **Replay consistency**: recomputing the score from history equals persisted state to four decimal places.

### Ablations

Seven configurations run the same eight chain tasks plus one injected weather failure:

| Configuration | Toggle |
|---|---|
| Full | All components enabled |
| No ontology | `use_ontology=false` |
| No Auditor | `use_auditor=false` |
| No trust | `use_trust=false` |
| No feedback | `use_feedback=false` |
| No substitution | `use_substitution=false` |
| No circuit breaker | `use_circuit_breaker=false` |

The report shows chain success, whether the injected failure recovered, whether the expected substitute ran, and latency. It is intentionally a behavioral ablation, not a statistical significance test.

## Current offline results

Generated by `python -m app.evaluation.run_all`:

| Suite | Size | Result |
|---|---:|---|
| Matching | 50 tasks / 67 links | Coverage 1.000, hit@k 1.000, top-1 1.000, MRR 1.000, selected-tool 1.000 |
| Chains | 15 tasks | Success 1.000, expected coverage 1.000, trace coverage 1.000, average 1.67 steps |
| Baselines | 15 tasks + fault case | Full, B1 and B2 all 1.000 on curated chains; fault recovery 1.000 full vs 0.000 B1/B2 |
| Substitution | 7 cases | Recovery accuracy 1.000, substitute accuracy 0.857, unexpected recovery 0.000 |
| Trust | 6 scenarios | Pass rate 1.000, demotion accuracy 1.000, replay consistency 1.000 |
| Ablations | 7 configurations | Chain success 1.000, recovery 0.714, substitution 0.714 |

Interpretation:

- Every seeded capability is discovered for the curated tasks.
- The full chain set completes offline.
- The three runners tie on easy curated chains, but only the full Client recovers from an injected provider outage.
- All six positive substitution cases recover through the expected mirror; the SQL outage correctly fails because no substitute exists.
- Disabling substitution prevents recovery, which is the expected causal ablation.
- Disabling the Auditor changes candidate evidence and can prevent the expected recovery path, showing that claim verification is part of the safety loop rather than decoration.
- The 0.857 substitute accuracy is intentional: the negative control has no substitute, so it is correct but not a substitution.

These results are a deterministic regression baseline. They do not measure the reliability of Open-Meteo, Frankfurter, Nominatim, REST Countries, Nager.Date or arXiv under real network conditions.

## Report shape

Each report contains:

```json
{
  "suite": "matching",
  "generated_at": "...",
  "mode": "offline",
  "tasks": 50,
  "metrics": {},
  "failures": [],
  "rows": []
}
```

`reports/summary.json` combines the six suites and a headline block. Raw rows are retained so a failed case can be inspected without rerunning the suite.

## Adding cases

1. Add an entry to the relevant JSON dataset.
2. Use only capabilities and tool IDs present in `app/data/ontology.json` and `app/data/tools.json`.
3. Keep IDs unique (`m51`, `c16`, `s08`, `t07`).
4. Run the suite and inspect `failures` before committing the report.
5. Add or adjust a pytest assertion only when the dataset contract changes.

Matching tasks should specify **primary** tools, not backup mirrors. Backup mirrors are exercised in the substitution suite.

## Known limitations

- The fixtures are deterministic and small, so ceiling effects are expected.
- Matching quality is measured against the curated expected tool, not against a human relevance judgment panel.
- Trust scenarios are synthetic and test the formula and persistence, not real provider calibration.
- Ablations run with fixed settings and no random sampling.
- Latencies are local orchestration times, not network latency.
