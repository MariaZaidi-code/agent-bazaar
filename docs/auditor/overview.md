# Agent Bazaar Auditor

Trust and drift auditor for third-party agent tools. It checks tool documentation against live or fixture responses, assigns one of four evidence labels, watches response schemas over time, and publishes trust updates that a client or registry can consume.

This package is the standalone implementation of the **Auditor and Monitoring Lead** workstream for Agent Bazaar, merged into the application repository under `src/agent_bazaar_auditor`. It is intentionally runnable with the Python standard library only: the default demo and evaluation need no API keys, no paid services, and no network access.

## Why this exists

Agent Bazaar lets agents call third-party tools. A tool can be wrong in several different ways:

- its documentation is inaccurate;
- the response schema changes without notice;
- a mapped field is renamed, removed, or changes type or unit;
- the provider returns a plausible but polluted `200` response;
- the provider is unavailable or flaps;
- the provider silently changes semantics, such as serving Fahrenheit while claiming Celsius.

The Auditor produces evidence for each claim and turns drift into machine-readable alerts. Downstream components can then re-map, substitute, or lower trust. The Auditor does not perform mapping or substitution itself.

## What is implemented

- **Claim extraction and verification** for 15 keyless APIs and 47 catalog claims.
- **Four labels:** `Verified`, `Supported`, `Contradicted`, `Unsupported`.
- **Deterministic probe checks:** authentication, response shape, field presence, type, unit, range, and observed limits.
- **Evidence retrieval and judging:** hashing embeddings, a document retriever, a deterministic evidence judge, and an optional LLM judge/extractor.
- **Probe harness:** safe GET requests, rate limits, cache, fixtures, XML/JSON parsing, and payload validation.
- **Drift monitoring:** rule checks and a schema-embedding detector operating together.
- **DriftAlert messages** with old and new descriptions, detector, severity, distance, round, and candidate rename.
- **TrustUpdate feed** with a local Beta-style ledger and optional HTTP registry delivery.
- **Mock providers** for normal, rename, remove, type change, unit change, garbage `200`, outage, flapping, dishonest, and exaggerated-claim behaviors.
- **Scheduler** with normal and unstable re-probe intervals and persistence.
- **Artifact store** for probes, verifications, drift alerts, trust updates, and reports.
- **HTTP API** for verify, monitor, probe, trust, and mock control.
- **Reproducible evaluation:** 60 claims, 20 injected drift scenarios, rule-only versus full comparison, false alarms, trust experiment, and cost notes.

## Quickstart on Windows

```powershell
cd agent-bazaar-auditor
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
agent-bazaar-auditor demo
agent-bazaar-auditor evaluate
```

If PowerShell blocks activation, run `Set-ExecutionPolicy -Scope Process Bypass` for the current terminal only.

The same setup is available as `.\scripts\setup.ps1`, followed by `.\scripts\run_demo.ps1` and `.\scripts\run_evaluation.ps1`.

The same commands work on macOS and Linux after creating `.venv` with `python3 -m venv .venv` and activating `.venv/bin/activate`.

## Useful commands

| Command | What it does |
| --- | --- |
| `agent-bazaar-auditor catalog` | List tools, categories, claims, and probe availability. |
| `agent-bazaar-auditor extract open-meteo` | Extract claims from one tool description. |
| `agent-bazaar-auditor verify open-meteo` | Verify all claims with offline fixtures. |
| `agent-bazaar-auditor verify open-meteo --live` | Verify with a live keyless HTTP probe. |
| `agent-bazaar-auditor probe ipify --live` | Probe one API and validate the payload. |
| `agent-bazaar-auditor monitor open-meteo --rounds 3` | Re-probe and report drift alerts. |
| `agent-bazaar-auditor demo` | Run healthy, dishonest, outage, and garbage-200 examples end to end. |
| `agent-bazaar-auditor evaluate` | Run claim, drift, and trust evaluations and write reports. |
| `agent-bazaar-auditor serve --mock` | Start the HTTP API with mock controls enabled. |

Add `--json` to machine-oriented commands. Use `--output-dir` and `--cache-dir` to redirect artifacts. Offline fixtures are the default; `--live` is explicit for verify, probe, and monitor. The evaluation always uses frozen offline data so results cannot drift with provider availability.

## Labels

The decision table is fixed in `src/agent_bazaar_auditor/decision.py`:

| Documentation | Probe | Label |
| --- | --- | --- |
| Contradicts | Any result | `Contradicted` |
| Supports | Agrees | `Verified` |
| Supports | Disagrees | `Contradicted` |
| Supports | Not probeable, not probed, or probe error | `Supported` |
| Silent | Agrees | `Supported` |
| Silent | Disagrees | `Contradicted` |
| Silent | Not probeable, not probed, or probe error | `Unsupported` |

An outage therefore does not automatically become `Contradicted`. If the documentation supports the claim but the probe cannot produce usable evidence, the honest label is `Supported`, not `Verified`.

## Evaluation snapshot

The checked-in snapshot was generated with:

```powershell
agent-bazaar-auditor evaluate
```

| Area | Result |
| --- | --- |
| Claims | 60/60 correct; accuracy 1.000; macro F1 1.000 |
| Claim coverage | 76.67% of all claims; 100% of probeable claims |
| Drift, rule-only | 17/20 scenarios detected |
| Drift, rule + embedding | 20/20 scenarios detected; correct detector 20/20 |
| Drift false alarms | 0/30 known-good variations in both modes |
| Trust experiment | 5/5 bad providers demoted; 0/5 honest providers demoted |

These are controlled results on a curated set. They show that the decision procedure and detectors match the frozen ground truth; they do **not** estimate how often real providers lie in the wild. See [the Auditor evaluation](evaluation.md) for the full snapshot, confusion matrix, scenario list, and limitations.

The claim set is `data/seeded_claims.json`:

- 32 real `Verified` claims;
- 8 real `Supported` claims;
- 10 seeded `Contradicted` claims;
- 10 seeded `Unsupported` claims.

The drift set is `data/drift_scenarios.json`: 4 renames, 4 removals, 2 type changes, 2 unit changes, 3 garbage-200 responses, 2 outages, 2 flapping providers, and 1 dishonest provider. Garbage-200 cases are the deliberate ablation: rules miss them, while embedding distance catches the changed schema.

## Architecture

```text
Tool docs ──> claim extraction ──> evidence retrieval ──> evidence judge
                                                        │
Tool API  ──> probe harness ──> payload validation ──────┤
                    │                                   ▼
                    ├──> baseline and rules ───────> decision table ──> VerifyResult
                    └──> schema embedding ─────────> drift alerts
                                                        │
                                                        ▼
                                              TrustUpdate feed / ledger
```

The Auditor is deliberately split into contracts rather than one large script. The main message types are `VerifyRequest`, `VerifyResult`, `DriftAlert`, `TrustUpdate`, `Feedback`, `CorrectionSubmit`, and `RepairRequest` in `src/agent_bazaar_auditor/messages.py`.

## Project layout

```text
src/agent_bazaar_auditor/
├── claims.py            claim extraction, evidence retrieval, judging
├── probes/              definitions, HTTP harness, cache, checks
├── drift/               baseline, rules, embeddings, combined detector
├── mocks/               controllable mock providers and registry
├── evaluation/          claim, drift, trust, metrics, run-all
├── auditor.py           end-to-end verification flow
├── api.py               standard-library HTTP API
├── trust.py             TrustUpdate feed and Beta-style ledger
├── scheduler.py         adaptive re-probe scheduling
├── store.py             JSON/JSONL artifact store
└── cli.py               command-line interface

data/                    frozen claim and drift datasets
docs/auditor/            overview, architecture, protocol, evaluation and setup docs
scripts/                 dataset generation and helper scripts
tests/                   Auditor and application pytest suites
.github/workflows/ci.yml GitHub Actions CI
.vscode/                 editor tasks and launch configurations
pyproject.toml           packaging and tool configuration
```
```

## HTTP API

Start the server:

```powershell
agent-bazaar-auditor serve --mock
```

Endpoints:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Version, tool count, baseline count, trust observations. |
| `GET` | `/tools` | Tool catalog and probe availability. |
| `GET` | `/probes` | Probe definitions and safe input. |
| `GET` | `/trust` | Trust leaderboard and feed summary. |
| `POST` | `/verify` | Verify all or supplied claims for a tool. |
| `POST` | `/monitor` | Re-probe and return a verification plus drift alerts. |
| `POST` | `/probe` | Probe one tool and return raw probe metadata. |
| `POST` | `/mock` | Change a mock provider behavior when `--mock` is enabled. |

Example:

```powershell
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/verify `
  -ContentType "application/json" `
  -Body '{"tool_id":"open-meteo"}'
```

## Configuration

All configuration is optional. Environment variables are read by `Settings.from_env()`:

| Variable | Default | Meaning |
| --- | --- | --- |
| `ABA_LIVE` | `false` | Use live HTTP probes by default. |
| `ABA_DATA_DIR` | `data` | Frozen claim and drift datasets. |
| `ABA_OUTPUT_DIR` | `outputs` | Artifacts and reports. |
| `ABA_CACHE_DIR` | `.cache` | Probe cache. |
| `ABA_DRIFT_MODE` | `full` | `full`, `rule_only`, or `embedding_only`. |
| `ABA_DRIFT_THRESHOLD` | `0.15` | Cosine-distance threshold for the embedding detector. |
| `ABA_EMBEDDING_DIMENSIONS` | `256` | Hashing-embedding dimensions. |
| `ABA_TRUST_DEMOTION_THRESHOLD` | `0.4` | Local ledger demotion threshold. |
| `ABA_TRUST_REGISTRY_URL` | empty | Optional HTTP trust registry endpoint. |
| `ABA_REQUEST_TIMEOUT` | `15` | Live HTTP timeout in seconds. |
| `ABA_SCHEDULER_BASE_INTERVAL` | `3600` | Clean re-probe interval. |
| `ABA_SCHEDULER_UNSTABLE_INTERVAL` | `300` | Unstable re-probe interval. |
| `ABA_LLM_BASE_URL` | empty | Optional OpenAI-compatible chat-completions base URL. |
| `ABA_LLM_API_KEY` | empty | Optional LLM key. Never commit it. |
| `ABA_LLM_MODEL` | empty | Optional model id. |

The offline path does not require any LLM variables. An LLM is used only for claim extraction or evidence judging when explicitly configured and selected by code that injects the LLM judge.

## Tests and quality checks

```powershell
python -m pytest
python -m ruff check .
```

The tests cover the decision table, nested path resolution, probe validation, unit disagreement, drift detection, garbage-200 ablation, trust scoring, scheduler recovery, the full evaluation, the API, and the CLI.

## Integration contracts

- **`VerifyResult`** carries claim assessments, coverage, probe metadata, notes, and drift alerts. Each assessment includes its claim, label, document stance, probe outcome, evidence, rationale, and probe checks.
- **`DriftAlert`** carries `tool_id`, `field_path`, `detector`, `old_description`, `new_sample`, `severity`, `distance`, `probe_round`, and `details`. The candidate rename appears in `details.candidate_path`.
- **`TrustUpdate`** carries `tool_id`, `outcome`, `reason`, optional `claim_id`, and optional numeric value. It is delivered to the local ledger and, if configured, an HTTP registry.

These are the hand-off points to the Mapper, Client, and trust registry. Re-mapping accuracy and substitution policy are outside this repository.

## Documentation

- [Architecture](architecture.md)
- [Evaluation](evaluation.md)
- [Protocol and message contracts](protocol.md)
- [Work-plan mapping](work-plan-mapping.md)
- [Demo guide](demo-guide.md)
- [GitHub and VS Code setup](github-setup.md)

## Limitations

- The 60-claim set is curated and the full score reflects that curation; real-world precision and recall must be measured on a larger, independently labelled sample.
- Drift is mostly evaluated on controlled injected changes because real keyless APIs rarely change inside a short project window.
- The embedding threshold is tuned on 30 synthetic known-good variations. Baseline collection should continue across days before a production threshold is frozen.
- The hashing embedder is deterministic and dependency-free, not a semantic transformer. The interface allows a stronger embedder to be substituted.
- The Auditor emits evidence and alerts; it does not re-map fields, rank providers, or replace a provider.
- Live probes can be rate-limited or unavailable. The harness caches and throttles requests, and fixtures keep the demo reproducible.

## Author

Qaim Hussnain, BS Artificial Intelligence, University of Central Punjab. Auditor and Monitoring Lead for Agent Bazaar (Proposal v1.3).

## License

MIT. See [LICENSE](../../LICENSE).
