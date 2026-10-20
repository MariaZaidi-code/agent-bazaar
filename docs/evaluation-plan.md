# Evaluation plan

This plan evaluates field-to-concept mapping, the learning effect of corrections,
drift re-mapping, and the cost of the mapping paths. It separates what the code
supports today from what still has to be built. No accuracy, F1, or learning-curve
result is claimed in this repository while the gold set has no labels.

Code: `src/agent_bazaar/evaluation/` (`dataset.py`, `metrics.py`,
`learning_curve.py`), `scripts/run_eval.py`, `data/eval/mapping_gold.jsonl`.

## 1. Current dataset status

| Property | Current value |
| --- | --- |
| File | `data/eval/mapping_gold.jsonl` |
| Rows | 916 |
| Distinct tools | 8 (the committed seed corpus) |
| Labelled rows (`gold_concept` non-empty) | 0 |
| `gold_unit` values | 0 |
| Splits | All `unlabelled` |
| Source | Flattened fields from the 8 seed specs in `data/specs/seed` |
| Id | `{tool_id}:{field_path}` |
| Fields stored | name, type, description, sample, source, prelabel |
| Direction stored | No; `to_field_spec` currently hardcodes `output` |

`scripts/run_eval.py` exits with `dataset has no gold labels yet` when every
`gold_concept` is empty. `--template` regenerates a template from `--specs`
(default `data/specs/seed`) and overwrites `--dataset`, so do not run it after
labels are added. The committed 916-row file was produced from the 8-spec seed
directory, which is the `--specs` default; it is **not** the 98-spec corpus.
Regenerate against `data/specs` only if the team wants full-corpus coverage, and
record which set a run used.

Consequence for the evaluation design: with only 8 tools, a tool-level
dev/test split leaves very few tools per split, and results describe the seed
corpus (geocoding, postal, open data, transport) rather than the domain mix of
the full corpus. Decide explicitly whether to label the seed only, regenerate
the template over `data/specs`, or label a stratified sample of the full corpus
before freezing splits.

Known template issue: input field paths are preserved in `id`, but
`to_field_spec()` sets `direction="output"`. Before the formal test run, add
`direction` to `MappingExample` (or derive it from the path at evaluation time)
and use it in `to_field_spec()`. Otherwise input paths are evaluated with the
wrong direction/provenance and unit expectations.

Known runner issue: `run_eval.py` and `run_learning_curve()` take the first
mapping for a field without checking `status`. A failed mapping is returned in
`result.mappings` with `status="unmapped"` but still carries the rejected
concept, so it can be scored as a successful concept prediction. Filter
`status != "unmapped"` before constructing predictions (the same rule applies to
the learning curve).

## 2. Unit of evaluation and labels

- Unit: one `(tool_id, field_path)` field.
- Gold concept: the ontology concept's local name or full IRI; use one convention
  consistently. The current metrics strip an IRI to its local part.
- Gold "no concept": use the literal `unmapped`. Do not leave `gold_concept`
  empty for an intentionally unmapped field, because empty means *unlabelled* and
  is excluded by `run_eval.py`. The metrics already normalize the literal
  `unmapped`.
- Gold unit: the expected unit for unit-bearing concepts; `null` for concepts
  that are not unit-bearing. Empty means unlabelled, not "no unit".
- Notes: use an extra field (for example `notes`) and validation status. Do not
  put annotator identities in the public dataset; keep a separate keyed sheet.

### Labelling protocol

1. Freeze a candidate sample before annotation. Include all four domains and
   both directions; do not sample only fields the heuristic already maps.
2. Two team members label at least 40 fields **blind**: they do not see the LLM
   pre-labels, each other's labels, or the Mapper output. At least one of the
   two should not be the person who tuned the Mapper.
3. Compute observed agreement and Cohen's kappa from paired labels **before**
   discussing disagreements. Record the result. If kappa is low, refine the
   ontology guidance and re-label a fresh sample; do not "fix" agreement by
   copying one annotator.
4. Resolve disagreements by discussion against the ontology definitions. Record
   the adjudicated label, not the pre-label.
5. Only after the blind set is complete may pre-labels be shown; use them to
   speed up the remainder, never as gold by default.
6. Split by tool, not by field, so the same API schema cannot appear in both dev
   and test. Proposed: 60% of labelled tools for dev, 40% for test; keep the test
   split frozen. The 40-field kappa set can overlap dev, but the test split must
   not be inspected during prompt/rule tuning.
7. Preserve the original unlabelled template. Store the labelled dataset and the
   split assignment in version control.

The helper is implemented:

```python
from agent_bazaar.evaluation.dataset import agreement_report

# pairs are aligned (annotator_a_label, annotator_b_label)
report = agreement_report(pairs)
print(report)  # n, agreements, observed, expected, kappa
```

Do not compute kappa between `gold_concept` and `prelabel`; that is model
agreement, not inter-annotator reliability.

## 3. Metrics

### Concept-level (implemented)

`compute_accuracy(predicted, gold)` returns n, correct, accuracy, macro
precision/recall/F1, micro precision/recall/F1, and labels.
`confusion_pairs()` returns the most frequent wrong predictions.
`surface_accuracy_by_group()` produces per-group reports; `domain_of_concept()`
groups concepts by keyword (geo, weather, currency, reference, other).

Use:

- **Accuracy**: headline, including `unmapped` as a label.
- **Macro F1**: treats every concept equally; important because many fields map
  to a few frequent concepts.
- **Micro F1**: in this single-label implementation micro precision, recall, and
  F1 all equal accuracy. Report it, but do not present it as an independent
  metric.
- **Coverage / abstention**: share of fields predicted `unmapped`, and share
  where gold is `unmapped`. These are not returned as a separate field; compute
  them from the prediction list.
- **Confusion pairs**: top errors, especially `unmapped -> concept` (missed
  mapping) and frequent-to-frequent substitutions.

### Unit-level (planned)

`gold_unit` exists but the current metrics ignore it. Add:

- unit accuracy on fields whose gold concept is unit-bearing;
- unit-family compatibility rate;
- unit exact-match rate when both sides have a unit;
- separate count for "concept correct, unit wrong".

Do not fold unit errors into concept F1; report them separately.

### Direction and domain slices

Report concept accuracy/macro F1 by `input`/`output`, by domain, by field type
(float/string/date/...), and by unit-bearing status. The existing domain grouping
is heuristic and may misclassify concepts; state that in the report.

### Calibration and uncertainty (planned)

- Reliability bins: confidence bucket vs empirical accuracy, with counts.
- Expected calibration error (ECE), if enough labelled points exist.
- Bootstrap confidence intervals for accuracy and macro F1 (resample fields).
- McNemar's test for paired variants (same fields, two systems).
- Do not compare systems on different subsets.

At 40-60 labelled fields, confidence intervals will be wide. Report n and the
interval; do not overstate small differences.

## 4. Splits and leakage

| Split | Purpose | Rules |
| --- | --- | --- |
| Dev | Prompt/rule/correction tuning | May be inspected repeatedly; keep correction fields out of held-out scoring |
| Test | Final report | Frozen before tuning; open once for the final run |
| Learning curve | Measures correction effect | Corrections from dev; held-out fields must not include the correction's own field |
| Drift set | Measures re-mapping | Inject known drift per field, do not reuse the original test label as the only gold |

With only 8 tools in the committed template, a 60/40 tool-level split leaves
about 5 dev tools and 3 test tools. That is too few for a stable split, so
either label a wider tool population first or accept a field-level split and
state the leakage risk explicitly.

Leakage risks:

- The same tool may have near-identical fields across endpoints; split by tool.
- Pre-labels may reflect the same model being evaluated; never treat them as
  gold.
- The 60-concept seed may have been designed with the same corpus; state that
  the test set is not fully independent of ontology development.
- Correction memory contains tool/field pairs; exclude those exact fields from
  the learning-curve evaluation (the helper does this by id).
- Evaluation ids are `tool:path`, while mapping paths are `path`; keep the
  lookup consistent. `run_eval.py` sets `FieldSpec.field_path=example.id`, so it
  works, but this means evaluation graph paths are not canonical spec paths.
  Document that this is an evaluation-only adaptation.

## 5. Experiments

### E0: Heuristic baseline (offline, reproducible)

```powershell
python scripts/run_eval.py --dataset data\eval\mapping_gold.jsonl
```

Uses hash embeddings, heuristic mapper, no LLM. Report accuracy, macro F1,
coverage, latency, and per-domain slices. This is the deterministic floor.

### E1: LLM zero-shot with retrieval

```powershell
python scripts/run_eval.py --dataset data\eval\mapping_gold.jsonl --llm
```

Requires a provider key and cache. Report provider/model, temperature, prompt
version, cache hit rate, tokens, latency, and errors. A cached run can be replayed
offline; record that it is a replay, not a fresh model call.

### E2: LLM + corrections (learning curve)

```powershell
python scripts/run_eval.py --dataset data\eval\mapping_gold.jsonl --llm --learning-curve
```

The helper trains on `split="dev"` correction examples and evaluates held-out
fields after 0, 5, 10, and 20 corrections. It resets memory and the correction
vector between counts, rebuilds the index, and excludes a correction's own field.
Report the curve and the count evaluated.

**Important:** the offline heuristic ignores correction hits. An offline learning
curve is expected to be flat by construction, so do not present it as evidence
that corrections do not help. Run the curve with the LLM path; if no key/cache is
available, report the curve as not run.

### E3: Repair ablation

Compare, on the same fields:

1. heuristic;
2. LLM, no repair (fail on first validation error);
3. LLM + one repair attempt;
4. LLM + full repair (default 3).

The current code always uses the configured repair loop on the LLM path, so E3
needs a controlled test harness or a temporary setting, not a production code
change. Report repaired share, final unmapped share, attempts, and latency.

### E4: Retrieval/candidate ablation

1. no retrieval (concept list only, if the prompt fits);
2. top-k terms only;
3. top-k terms + corrections;
4. top-k changes (for example 5 vs 12).

Vary one factor at a time. Do not infer that more candidates are always better;
long prompts increase cost and can distract the model.

### E5: Unit handling ablation

1. default unit from the concept;
2. LLM-proposed unit;
3. default unit plus deterministic family correction.

Report concept-level and unit-level metrics separately. The current Mapper
defaults the unit when the model omits it and rejects incompatible units; compare
that policy with a strict "no default" policy.

### E6: Drift re-mapping

Build a small drift set by taking labelled fields and injecting controlled
changes: renamed field, changed sample type, changed unit hint, changed
description. The Auditor's detector is not in this repository; this experiment
starts from a `DriftAlert`. Report:

- concept accuracy after re-map against the drift gold;
- share left unmapped/queued;
- share where the old concept was retained;
- latency per alert;
- `drift_accuracy()` results.

Do not claim end-to-end drift detection performance without Qaim's detector.

### E7: Cost and latency

Report per-field and per-batch:

- wall-clock mean/median/p95/max (`latency_stats`);
- LLM calls, cache hits, errors, prompt/completion tokens
  (`LLMClient.stats`; `token_stats` exists but is not wired into `run_eval.py`);
- embeddings used (model or hashing) and vector counts;
- SHACL validation time, separately from mapping time.

The accepted architecture trades a slower validation pass for correctness and a
simpler shape set; see
[decisions.md](decisions.md#adr-011-class-target-shacl-plus-deterministic-checks-performance-trade-off).
Report validation separately so that cost is not hidden.

## 6. Analysis procedure

1. Freeze the test split and record the dataset hash.
2. Run E0 and E1 on dev first; inspect confusions and per-domain failures.
3. Make at most the planned prompt/rule changes; record each change.
4. Run the learning curve with the LLM path on dev.
5. Freeze the system and run once on test. Do not tune after seeing test results.
6. Report point estimates with n and bootstrap intervals; include an error table,
   not only the headline number.
7. Archive the exact command, provider/model, embedding mode, cache status,
   dataset hash, and code commit.

## 7. Acceptance gates

Numeric model targets are intentionally not set before a dev baseline exists;
setting them now would invite tuning to the test set. Process gates:

- At least 40 fields double-labelled blind; kappa and agreement reported.
- Test split frozen and tool-disjoint from dev.
- Every reported number has n and the exact command.
- No accuracy/F1 claim while gold labels are absent.
- Unit metrics reported separately from concept metrics.
- Learning curve reported only for a path that actually consumes corrections, or
  explicitly marked not applicable.
- Failures and unmapped share reported alongside success metrics.
- Cost, cache status, and latency reported for LLM results.
- Known limitations from [decisions.md](decisions.md) repeated in the report.

After the dev baseline, the team can agree on a target (for example a macro-F1
floor and a maximum unmapped share) and record it here before opening test.

## 8. Threats to validity

| Threat | Effect | Mitigation |
| --- | --- | --- |
| Small label set | Wide confidence intervals | Label more; report CIs; avoid over-ranking close systems |
| Ontology designed with corpus knowledge | Test is not fully independent | Say so; use held-out tools and external specs later |
| Heuristic domain grouping | Slices may be wrong | Manually verify group assignments for reported slices |
| Pre-label anchoring | Inflated human agreement | Blind labelling first; kappa before discussion |
| Cache replay mistaken for live calls | Cost/latency understated | Label runs as cached/replayed; report cache hits |
| Different embedders across runs | Distances/vectors incomparable | Record embedder and dimension; rebuild on change |
| LLM/provider drift | Results not reproducible later | Cache prompts/responses; record model/version/date |
| Evaluation path adaptation | Not identical to production field paths | State limitation; add direction and canonical paths |
| Single-label micro F1 | Looks like a second metric but equals accuracy | Label it correctly in tables |
| Seed-only graph | Does not represent 98-spec coverage | Distinguish seed evaluation from full-corpus claims |
| Seed-only evaluation template | 916 rows cover 8 tools, so the labelled set would be geocoding/open-data heavy | Decide the labelled population before splitting; report the tool list with results |

## 9. Reporting template

```markdown
## Mapping evaluation

- Code commit:
- Dataset: data/eval/mapping_gold.jsonl (sha256, n labelled, split counts)
- Ontology: data/out/ontology.ttl (source seed/mixed, concepts, violations)
- Mapper: heuristic | LLM provider/model, temperature, cache hits
- Embedder: model/dimension or hashing

| Variant | n | Accuracy | Macro F1 | Unmapped share | Mean latency | p95 |
| --- | --- | --- | --- | --- | --- | --- |
| E0 heuristic | | | | | | |
| E1 LLM | | | | | | |

### By domain
### Top confusions
### Unit accuracy
### Learning curve (if applicable)
### Cost
### Limitations
```

## 10. Current blockers and next steps

1. Add `direction` to the evaluation example and use it in `to_field_spec`.
2. Label at least 40 fields blind; compute kappa; adjudicate.
3. Freeze tool-level dev/test splits.
4. Run E0 and E1 on dev; inspect errors.
5. Run the LLM learning curve; do not use the offline curve as evidence.
6. Add unit metrics and a paired significance test.
7. Build the drift set with Qaim; evaluate re-mapping after the detector exists.
8. Only then open the frozen test split and report.

Current blockers: 0 gold labels, no direction field, the runner does not filter
failed mappings, the template covers only the 8 seed tools, no unit metric, no
drift dataset, no controlled LLM benchmark, and no agreed numeric target.

## References

- Dataset helpers: `src/agent_bazaar/evaluation/dataset.py`
- Metrics: `src/agent_bazaar/evaluation/metrics.py`
- Learning curve and ablations: `src/agent_bazaar/evaluation/learning_curve.py`
- Runner: `scripts/run_eval.py`
- Template: `data/eval/mapping_gold.jsonl`
- Mapper protocol: [mapper-protocol.md](mapper-protocol.md)
- Decisions: [decisions.md](decisions.md)
