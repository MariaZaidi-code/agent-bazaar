# Evaluation plan

This plan evaluates field-to-concept mapping, the learning effect of corrections,
drift re-mapping, and the cost of the mapping paths. It separates what the code
supports today from what still has to be built. No accuracy, F1, or learning-curve
result is claimed in this repository while the gold set has no labels.

Sections 1 to 10 cover the knowledge-layer mapping evaluation. Section 11
covers the free-first ranking evaluation of the application layer, which is a
separate suite with its own dataset, its own metrics and its own ablations.

Code: `src/agent_bazaar/evaluation/` (`dataset.py`, `metrics.py`,
`learning_curve.py`), `scripts/run_eval.py`, `data/eval/mapping_gold.jsonl`,
`app/evaluation/run_ranking.py`, `app/evaluation/metrics.py`,
`app/evaluation/data/ranking_tasks.jsonl`.

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

## 11. Ranking evaluation: free-first ranking

The mapping evaluation above measures the knowledge layer. A second suite
measures the ranking behaviour that the commercial, access and documentation
facts feed: does the Client put a free tool above a paid one, does it keep the
ranking executable, and is the order the one a human would choose?

Code: `app/evaluation/run_ranking.py`, `app/evaluation/data/ranking_tasks.jsonl`,
`app/agents/ranking_policy.py`, `app/evaluation/metrics.py` (`mean`, `ratio`).

```powershell
python -m app.evaluation.run_ranking
```

The suite replays a hand-checked dataset of ranking tasks through
`rank_candidates()` and writes `reports/ranking.json`. It is offline and
deterministic; it is not part of `app.evaluation.run_all`, so it is run
separately.

### 11.1 The dataset

`app/evaluation/data/ranking_tasks.jsonl` holds one JSON object per line with
a `task`, a `capability`, a list of `candidates`, an `expected_order` and a
`notes` field explaining the expected order in words.

| Property | Value |
| --- | --- |
| Tasks | 48 |
| Capabilities | 8, 6 tasks each: `GeocodeLocation`, `GetWeatherForecast`, `ConvertCurrency`, `GetCountryFacts`, `GetPublicHolidays`, `SearchResearchPapers`, `QueryStructuredData`, `AnswerFromDocument` |
| Candidate rows | 149 |
| Distinct tool ids | 46 |
| Candidates per task | 3 in 43 tasks, 4 in 5 tasks |
| Candidate tiers | free 92, paid 34, freemium 15, unknown 8 |
| Candidate access requirements | keyless 103, api_key 20, paid_key 26 |
| Tasks with at least one free candidate | 48 of 48 |
| Claim labels | supported 137, unsupported 8, contradicted 4 |
| Candidates with a demoted provider | 3 |
| Candidates with an open circuit breaker | 1 |
| Candidates with fewer than 3 reviews | 34 |

Each candidate carries the facts the policy weighs: `relevance`, `trust`,
`pricing_tier`, `access_requirement`, `rating_value`, `rating_count`,
`doc_quality`, `mapping_coverage`, `chain_fit`, `claim_label`, `demoted`,
`breaker_open` and `licence`.

The dataset is hand-written, so the numbers below describe the policy on a
curated set of 48 tasks. They are not a claim about live internet behaviour and
not a claim about the 98-document corpus.

### 11.2 The metrics

| Metric | Definition |
| --- | --- |
| `mrr` | Mean reciprocal rank of the expected best tool, the first entry of the task's `expected_order`, in the ranked list |
| `ndcg_at_10` | Normalised discounted cumulative gain at 10 with graded gains: the gain of a ranked candidate is `len(expected_order) - position` in the expected order, so the expected best tool carries the largest gain. `DCG = sum(gain_i / log2(i + 1))` over the first ten positions, `IDCG` is the same sum over the expected order itself |
| `free_first_rate` | Share of tasks that had at least one free candidate and whose top ranked candidate is in the free tier |
| `executable_top_rate` | Share of tasks whose top ranked candidate is executable, that is free and keyless under the policy in force |
| `tier_separation_accuracy` | Share of tasks whose ranked list never places a candidate from a lower tier above a candidate from a higher tier, using the canonical tier order free > freemium > paid > unknown |

Graded gains are what make the NDCG sensitive to a wrong order. Because the
expected order is a full permutation of the candidates, binary gains would be
1.0 for every ranking.

### 11.3 The ablations

| Configuration | Override |
| --- | --- |
| `full` | The default policy |
| `no_tier` | `pricing_policy="ignore"`: the tier stops being a sort key |
| `no_quality` | The documentation, mapping and chain-fit weights are zero |
| `no_rating` | `min_rating_count` is raised so the rating factor is always neutral |

### 11.4 The measured results

Command: `python -m app.evaluation.run_ranking`, dataset
`app/evaluation/data/ranking_tasks.jsonl`, default policy.

| Configuration | MRR | NDCG@10 | Free-first rate | Executable-top rate | Tier separation accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| `full` | 1.0000 | 1.0000 | 1.0000 | 0.9583 | 1.0000 |
| `no_tier` | 0.6771 | 0.8823 | 0.3542 | 0.3333 | 0.2292 |
| `no_quality` | 0.7049 | 0.9478 | 1.0000 | 0.9375 | 1.0000 |
| `no_rating` | 0.9896 | 0.9984 | 1.0000 | 0.9583 | 1.0000 |

The report's failure list is empty: `failures: 0`. A failure is a task that is
not free-first or whose ranked order differs from the expected order.

Per capability, with the full policy:

| Capability | Tasks | MRR | NDCG@10 | Free-first rate | Executable-top rate | Tier separation accuracy |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `AnswerFromDocument` | 6 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `ConvertCurrency` | 6 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `GeocodeLocation` | 6 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `GetCountryFacts` | 6 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `GetPublicHolidays` | 6 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |
| `GetWeatherForecast` | 6 | 1.0000 | 1.0000 | 1.0000 | 0.8333 | 1.0000 |
| `QueryStructuredData` | 6 | 1.0000 | 1.0000 | 1.0000 | 0.8333 | 1.0000 |
| `SearchResearchPapers` | 6 | 1.0000 | 1.0000 | 1.0000 | 1.0000 | 1.0000 |

### 11.5 How the free-first behaviour is validated

The free-first behaviour is validated in four independent ways:

1. **The free-first rate.** Every one of the 48 tasks has at least one free
   candidate, and with the full policy the top ranked candidate is free in all
   48. The `no_tier` ablation drops the rate to 0.3542, so the number is a
   property of the tier partition and not of the dataset.
2. **Tier separation accuracy.** With the full policy no task ever places a
   lower tier above a higher one (1.0000); without the partition 0.2292 of the
   tasks do.
3. **The executable-top rate.** 46 of 48 tasks have an executable top
   candidate. The two exceptions are tasks whose strongest free candidate needs
   a key: `key-required-weather-pro` for "What is the weekend temperature in
   Berlin?" and `campus-sql-cloud-tier` for "How many students are enrolled in
   the university database?". Both keep the expected order and both are
   recorded as not executable, so the Client skips them and continues down the
   shortlist.
4. **The stored reasons.** Every ranked candidate records the reasons of its
   decision, including the pricing tier, the access requirement, the rating
   (or the reason the rating was not used), the documentation quality, the
   mapping coverage, the chain fit, the trust, and the reason a candidate is
   not executable. A ranking that cannot explain itself fails the requirement,
   and the reasons are part of the report rows.

The `no_quality` ablation isolates the quality factors: the free-first rate
stays at 1.0000 while the MRR falls from 1.0000 to 0.7049 and the NDCG@10 from
1.0000 to 0.9478. The `no_rating` ablation isolates the rating: the MRR falls
to 0.9896 and the NDCG@10 to 0.9984, because 34 of the 149 candidate rows
carry fewer than three reviews and are already ignored by the default policy.

### 11.6 Threats to validity

| Threat | Effect | Mitigation |
| --- | --- | --- |
| The dataset is hand-written | The expected orders encode one reviewer reading | The notes field states the reason for each expected order; extend the dataset and re-run |
| 48 tasks over 46 tool ids | A single tool family dominates some capabilities | Add tasks per capability as the corpus grows; report the composition with every run |
| The candidates are synthetic | The corpus tools have no ratings and no mapping coverage | The suite measures the policy, not the corpus; it does not claim corpus quality |
| No live calls | The executable-top rate says nothing about live availability | The live behaviour is the manual integration check; the suite is deterministic and offline |
| The rating has no effect in practice | The corpus holds no ratings | The `no_rating` ablation quantifies what the rating is worth once it exists |

### 11.7 Open items

- The dataset covers the 8 curated capabilities of the application only. The
  corpus's other capabilities are not represented.
- The rating ablation is small because the dataset's ratings are few and
  mostly below the minimum review count. A dataset with realistic rating
  distributions would give the rating a sharper measurement.
- There is no metric for the reason quality itself. The reasons are recorded
  and checked for presence, but there is no automated measure of whether a
  reason explains the right thing.
- The ranking suite is not part of `run_all`; a reviewer who only runs the
  application suites will not see it.

## References

- Dataset helpers: `src/agent_bazaar/evaluation/dataset.py`
- Metrics: `src/agent_bazaar/evaluation/metrics.py`
- Learning curve and ablations: `src/agent_bazaar/evaluation/learning_curve.py`
- Runner: `scripts/run_eval.py`
- Template: `data/eval/mapping_gold.jsonl`
- Ranking runner: `app/evaluation/run_ranking.py`
- Ranking dataset: `app/evaluation/data/ranking_tasks.jsonl`
- Ranking policy: `app/agents/ranking_policy.py`
- Mapper protocol: [mapper-protocol.md](mapper-protocol.md)
- Sourcing and reasoning: [api-sourcing-and-reasoning.md](api-sourcing-and-reasoning.md)
- Decisions: [decisions.md](decisions.md)
