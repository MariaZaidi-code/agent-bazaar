# API sourcing, quality profiling and free-first reasoning

This document describes how the project obtains API descriptions, how it turns
them into commercial, access and documentation facts, how those facts are stored
in the knowledge graph, and how the Client reasons over them without asking a
language model to do the arithmetic.

Code: `src/agent_bazaar/ingestion/sources.py`,
`src/agent_bazaar/ingestion/listing_metadata.py`, `scripts/fetch_specs.py`,
`data/overrides/pricing.yaml`, `data/specs/probe_set.json`,
`src/agent_bazaar/kg/quality.py`, `src/agent_bazaar/kg/store.py`,
`src/agent_bazaar/ontology/upper.ttl`, `src/agent_bazaar/ontology/shapes.ttl`,
`app/agents/ranking_policy.py`, `app/agents/client.py`, `app/config.py`,
`app/evaluation/run_ranking.py`.

## 1. Scope

The proposal requires three things that are easy to conflate:

1. **Sourcing.** A corpus of API descriptions with a determinate acquisition
   path, a recorded licence and terms position, and a refresh procedure that
   says what changed.
2. **Profiling.** Per-tool facts about what the API costs, whether a key is
   needed, what its rate limit is, and how good its documentation is.
3. **Reasoning.** A ranking that prefers free tools, keeps paid tools visible
   but never calls them, and can explain every decision from stored evidence.

The separation matters for the project's non-functional requirements. The
ranking arithmetic has to be deterministic and reproducible (FR3, NFR4), the
project must not spend money on API calls (NFR1), and a provider's terms must
be checked before its service is used (Proposal Section 4). Those three
constraints pull in different directions unless each stage is kept separate:

- sourcing produces bytes and provenance,
- profiling produces facts with evidence,
- the graph stores the facts,
- the policy weighs the facts.

The language model is used for planning and for the answer text. It never
produces a rank and it never sets a commercial fact.

## 2. How APIs are obtained

### 2.1 Sources

`src/agent_bazaar/ingestion/sources.py` defines a `SpecSource` protocol:

```python
@runtime_checkable
class SpecSource(Protocol):
    name: str
    source_id: str
    licence_policy: str

    def list_candidates(self) -> list[dict[str, Any]]: ...
    def fetch(self, entry: dict[str, Any]) -> bytes: ...
```

Every source is identified, states its licence policy, enumerates candidates in a
deterministic order, and returns the raw bytes of one candidate. Two sources
ship with the project:

| Source | `source_id` | What it lists | Licence policy it declares |
| --- | --- | --- | --- |
| `ApisGuruSource` | `apis-guru` | The public APIs.guru directory, one entry per API at its preferred version, keyed and sorted | Third-party API descriptions; each document keeps its own provider's licence and terms, and redistribution needs the provider's permission |
| `LocalUploadSource` | `local-upload` | Provider-submitted specifications in a local directory (`.json`, `.yaml`, `.yml`), sorted by path, `manifest.json` excluded | Specification submitted by the provider; the provider keeps the copyright |

`BaseSpecSource.check_payload()` rejects a payload larger than 1,500,000 bytes
or one whose first 2,000 characters contain neither `"openapi"` nor
`"swagger"`. A rejected payload raises `SourceError` and is skipped, never
half-written.

### 2.2 Determinism

The corpus build is reproducible from a seed:

```powershell
python scripts/fetch_specs.py --limit 100
```

- The APIs.guru listing is read from `https://api.apis.guru/v2/list.json` with
  the user agent `agent-bazaar-corpus/0.1`.
- `ApisGuruSource.entries_from_listing()` sorts the listing keys and keeps each
  API's `preferred` version, so the candidate list does not depend on the
  upstream JSON order.
- `select_entries()` splits the candidates into priority categories (`weather`,
  `location`, `geocoding`, `maps`, `currency`, `finance`, `government`,
  `open_data`, `data`, `geography`) and the rest, shuffles each group with
  `random.Random(seed)` and takes half the limit from the priority group. The
  default seed is 42.
- The final selection is sorted by API key before it is written, so the manifest
  order does not depend on the shuffle.
- Files already present are reused unless `--force` is passed.

The seed corpus is chosen separately and prefers keyless and free tools.
`select_seed_files()` ranks the eligible candidates by

```text
(seed_preference, preferred-file order, -keyword score, bytes, file name)
```

where `seed_preference` is `0` for a keyless tool whose tier is `free` or
`unknown`, `1` for a keyless tool in another tier, and `2` for a tool that
needs a key. The chosen reason is written into the manifest as `seed_reason`,
so the choice can be reviewed later rather than taken on trust. The committed
seed manifest records that reason in prose, for example:

```text
deutschebahn-com-fahrplan.json | keyless + free tier; preferred seed file; keyword score 0 (no keyword match)
miataru-com.json                | keyless + unknown tier; preferred seed file; keyword score 5 (location)
```

The current seed corpus holds 8 documents: 4 `free`, 1 `freemium`, 3
`unknown`; 2 keyless, 5 `api_key`, 1 `paid_key`.

### 2.3 Licensing and terms checks

Each source declares a licence policy, and each source entry carries the
provider's own declarations forward:

- `info.license` gives the licence name and, when present, the licence URL.
- `info.termsOfService` gives the terms URL and wins over the licence URL.
- The document's declared licence and terms URL are stored on the offering
  (`ab:licence`, `ab:termsUrl`), not just in the manifest.

This is a provenance record, not a legal review. The corpus note in
[`../data/specs/README.md`](../data/specs/README.md) states the same position:
provider metadata is not a legal opinion, and AGPL/LGPL or custom terms can
restrict redistribution or derived use. The curated override file records a
`reviewer` and a `checked_at` for each human-checked entry; every current
entry has an empty `reviewer`, so **no human has signed the licences off yet**
and the corpus manifest keeps `licence_reviewed_at` empty as well.

### 2.4 Manifest v2, refresh and diff

The corpus manifest is version 2. Each entry keeps the descriptive fields of
manifest v1 and adds the commercial, access and documentation facts:

| Field | Source |
| --- | --- |
| `manifest_version` | `2` |
| `pricing_tier` | `free`, `freemium`, `paid`, `unknown` |
| `access_requirement` | `keyless`, `api_key`, `paid_key` |
| `price_amount`, `price_currency` | The published price, if the document states one |
| `rate_limit_policy` | The published limit, in words |
| `probe_budget_per_minute` | Requests per minute this project may send |
| `licence`, `terms_url` | The document's own declarations |
| `doc_quality`, `operation_count`, `deprecated_operations`, `spec_version` | Measured from the document |
| `source`, `selection_rule_version`, `licence_reviewed_at` | Acquisition and review bookkeeping |
| `seed`, `seed_reason` | Set on the entries copied into the committed seed |

Two modes rebuild the manifest without touching the network:

```powershell
python scripts/fetch_specs.py --metadata-only   # re-extract the facts of the downloaded specs
python scripts/fetch_specs.py --refresh          # rebuild the manifest and write the diff
```

`--refresh` writes `data/out/logs/corpus_refresh.json`, which contains the
added, removed, changed and version-changed entries together with the counts.
The committed report records the upgrade from manifest v1 to v2 over the same
98 documents:

| Count | Value |
| --- | ---: |
| `previous_manifest_version` | 1 |
| `manifest_version` | 2 |
| added | 0 |
| removed | 0 |
| changed | 98 |
| version_changed | 98 |
| previous / current documents | 98 / 98 |

`changed` is 98 because every entry gained the v2 fact fields; `version_changed`
is 98 because the entry now carries the extracted `spec_version` beside the
upstream API version. A later refresh with real upstream movement produces
non-zero `added`, `removed` and `version_changed` counts.

Other useful switches: `--overrides <path>` points at a different curated
override file, `--source local --local-dir <dir>` ingests provider-submitted
specifications instead of the public directory, and `--report <path>` writes the
refresh report somewhere else.

### 2.5 The probe set

`data/specs/probe_set.json` is the curated list of tools that may be called
live. The selection rule is fixed and stated in the file:

> Keyless means the corrected extraction rules of
> `agent_bazaar.ingestion.listing_metadata` find no security scheme, no global
> security requirement, no required credential parameter, no platform host and
> no statement about a key in the prose.

Only such a tool may be probed, because a probe of a keyed tool fails without a
credential. The file also records the correction that produced it: the earlier
list wrongly kept `ideal-postcodes-co-uk`, `geodatasource-com`,
`interzoid-com-getzipinfo`, `nexmo-com-pricing` and `europeana-eu`, and the
corrected rules detect the credential in each of them and drop all five.

The set holds **11 of the 12 to 15 tools the proposal asks for**. The corpus in
`data/specs` holds 98 documents and exactly 11 of them are keyless, so the
shortfall is one tool and no further extraction rule can close it: the corpus
needs another keyless document.

| Capability covered | Keyless tools |
| --- | --- |
| `GeocodeLocation` | `deutschebahn-com-fahrplan`, `deutschahn-com-flinkster`, `miataru-com` |
| `GetWeatherForecast` | `oceandrivers-com` |
| `SearchResearchPapers` | `cybertaxonomy-eu`, `ideaconsult-net-nanoreg`, `parliament-uk-search`, `parliament-uk-bills` |
| Mechanical keyless probes (no curated capability) | `balldontlie-io`, `crediwatch-com-covid19`, `moderatecontent-com` |

`ConvertCurrency` and `GetPublicHolidays` are not covered by the probe set:
`nexmo-com-pricing` was the only currency source in the corpus and it needs
`api_key` and `api_secret` parameters, and no keyless document in the corpus
publishes public holidays, which the application covers with the Nager.Date
provider instead.

## 3. How commercial and access facts are extracted and reviewed

`src/agent_bazaar/ingestion/listing_metadata.py` extracts the facts from an
OpenAPI document with deterministic rules. It returns a `ListingMetadata`
record with the pricing tier, the access requirement, the price, the rate
limit and probe budget, the licence and terms URL, the documentation quality
with its sub-scores, and two evidence lists.

### 3.1 The three rules that matter

1. **Absence of pricing evidence never means free.** A specification that says
   nothing about pricing becomes `unknown`, with the evidence
   `"no pricing statement found"`. The `unknown` tier is a real answer.
2. **A credential parameter only implies a key when it is required.** An
   optional `api_key` parameter means "you may pass a key", not "a key is
   needed", so the listing stays keyless for live probing. A credential is
   recognised when the parameter is required and its name is a known credential
   name, when it is required and its description mentions a credential, or when
   a strong credential name is described as a credential.
3. **Authentication stated in prose is detected.** Phrases such as "requires an
   API key", "a key is required" or "sign up to get an API key" are matched and
   recorded as evidence.

### 3.2 Pricing tier

The text blob is the document's `info.title`, `info.description`,
`info.summary`, `info.termsOfService`, the theme fields, and the top-level
`description`/`summary`. Three pattern families are matched:

| Tier | Trigger |
| --- | --- |
| `freemium` | A freemium pattern, or a free pattern **and** a paid pattern in the same document |
| `paid` | A paid pattern only: `pricing plan`, `subscription required`, `premium tier`, `per month`, `per 1,000 requests`, a currency amount, `credits required`, `requires a paid/commercial/subscription` plan |
| `free` | A free pattern only: `free tier`, `free plan`, `free for non-commercial use`, `no key required`, `without an api key`, `open data`, `no charge` |
| `unknown` | None of the above |

The free patterns deliberately exclude "free for N days" and "trial only", so a
time-limited trial is not recorded as free.

### 3.3 Access requirement

The access requirement is derived from the security schemes first, then from
the credential parameters and the prose, then from the platform host:

| Signal | Result |
| --- | --- |
| A security scheme of type `apikey`, `http`, `oauth2`, `openidconnect` or `mutualtls`, or a scheme named like a key | `api_key`, or `paid_key` when the tier is `paid` or `freemium` |
| A required credential parameter, or an authentication statement in prose | `api_key`, or `paid_key` when the tier is `paid` or `freemium` |
| Any security scheme, or a global `security` requirement | `api_key` |
| A platform host (`googleapis.com`, `azure.com`, `azure-api.net`, `amazonaws.com`, `digitalocean.com`, `twilio.com`, `sendgrid.net`, `mailgun.org`, `stripe.com`, `shopify.com`, `slack.com`, `dropboxapi.com`, `github.com`, `openai.com`) | `api_key` |
| None of the above | `keyless` |

A `paid_key` is a keyed tool whose provider also sells a paid plan. The
difference matters because a `paid_key` must not be executed at all, while an
`api_key` on a free tier is only blocked because no credential is available in
this project.

### 3.4 Price, rate limit and probe budget

- **Price.** The first match of a price pattern wins. A code (`usd`, `eur`,
  `gbp`, `jpy`, `inr`, `aed`, `pkr`) gives an explicit currency; a symbol
  (`$`, `€`, `£`, `¥`, `₹`) is mapped to `USD`, `EUR`, `GBP`, `JPY`, `INR`.
- **Rate limit.** A quota pattern such as "1000 requests per day" or "rate
  limit of 60" is rendered as a policy string such as
  `"1000 requests per day"`.
- **Probe budget.** The same number is converted to requests per minute
  (`per second` x 60, `per minute` x 1, `per hour` x 1/60, `per day` x 1/1440,
  `per month` x 1/43200), rounded, and clamped to at least 1. This is the
  ceiling the project imposes on itself, not a number the provider promises.

### 3.5 Documentation quality

Documentation quality is measured from the specification itself, so the score
is reproducible for every corpus member and needs no human in the loop. Seven
sub-scores are combined with fixed weights:

| Sub-score | Weight | Measurement |
| --- | ---: | --- |
| `description` | 0.25 | Length of `info.description`, capped at 400 characters |
| `field_descriptions` | 0.20 | Share of schema properties that carry a description |
| `typed_io` | 0.15 | Share of parameters and request bodies that declare a schema or a type |
| `response_schemas` | 0.15 | 1 when any response declares content or a schema |
| `examples` | 0.05 | 1 when the paths contain an example |
| `not_deprecated` | 0.05 | 1 when no operation is marked deprecated |
| `breadth` | 0.15 | Operation count divided by 10, capped at 1 |

The weighted sum is the `doc_quality` value between 0 and 1; the sub-scores are
kept next to it so a low score can be explained.

### 3.6 Evidence lists

Every extraction carries its evidence:

- `tier_evidence` holds the matched pricing fragments, or
  `"no pricing statement found"`.
- `access_evidence` holds the security schemes, the declared credential
  parameters, the prose statement, the platform host, or the explicit
  `"no security scheme, credential parameter or platform rule matched"` for a
  keyless listing.

The evidence is stored in the graph (`ab:tierEvidence`, `ab:accessEvidence`) and
is what makes a ranking decision explainable later.

### 3.7 Curated overrides

`data/overrides/pricing.yaml` is the human layer. A curated entry always wins
over the extracted value, and the fields it may set are `pricing_tier`,
`access_requirement`, `price_amount`, `price_currency`, `rate_limit_policy`,
`probe_budget_per_minute`, `licence` and `terms_url`. Each entry carries
`reviewer`, `checked_at` and `note`.

The file covers the eight live application providers and three corpus tools
whose earlier classification the corrected rules changed:

| Tool | Tier | Access | Note in the file |
| --- | --- | --- | --- |
| `open-meteo-forecast` | free | keyless | Free for non-commercial use, CC-BY 4.0, commercial use needs a paid plan |
| `frankfurter-currency` | free | keyless | Free, keyless, usable commercially, MIT |
| `nominatim-geocode` | free | keyless | Needs a valid `Referer`/`User-Agent`, 1 request per second, ODbL |
| `restcountries-facts` | free | keyless | v3.1 endpoint needs no key; no single licence name can be supported |
| `nager-holidays` | free | keyless | MIT, unlimited queries, sponsorship asked for commercial use |
| `arxiv-search` | free | keyless | One request every three seconds, metadata under CC0 1.0 |
| `university-sql` | free | keyless | Local read-only sample database, no external provider |
| `document-qa` | free | keyless | Local extraction over an uploaded document |
| `ideal-postcodes-co-uk` | freemium | paid_key | Most requests require a key next to a free test balance and paid requests |
| `citycontext-com` | free | api_key | Declares a `user_key` security scheme, names no licence |
| `iptwist-com` | unknown | api_key | Declares an `ApiKeyAuth` scheme, says nothing about pricing |

Every one of those entries currently has an empty `reviewer`, so the file
records the checked facts but not a signed-off review.

## 4. How the facts are stored in the graph

The facts live on one `ab:Offering` node per tool. The full schema is in
[graph-schema.md](graph-schema.md#7-offering-nodes-commercial-access-and-documentation-facts);
the summary is:

- `ab:Offering` is a new upper-level class, added after the Week 3 ontology
  freeze as a versioned extension. The frozen 60-concept domain layer and the
  minimum shape set are unchanged.
- `ab:hasOffering` links a tool to its offering, and `ab:ToolOfferingShape`
  allows at most one offering per tool.
- `ab:OfferingShape` requires exactly one pricing tier and exactly one access
  requirement, and constrains the rating, the documentation quality, the
  mapping coverage and the probe budget to their ranges.

The write path is the same validated path as every other graph write. `write_tool()`
calls `_write_offering()`, which **skips the offering entirely** when the
record's access requirement is not one of `keyless`, `api_key` or `paid_key`:
absence of evidence is never read as "free", and a tool without a known access
requirement keeps no offering node at all.

`KgStore.update_tool_quality()` updates the offering in one candidate graph and
commits it through the same SHACL validation, so an offering that violates the
shapes is rejected and the current graph is left untouched. It can write the
rating value, the rating count, the rating source, the documentation quality,
the mapping coverage, the licence, the pricing tier and the access
requirement, and it returns the refreshed profile.

`KgStore.tool_quality_profile(tool_id)` reads the offering back as a
`ToolQualityProfile`: the tier, the access requirement, the price, the rate
limit, the probe budget, the rating with its confidence, the documentation
quality and its sub-scores, the mapping coverage, the licence, the terms URL,
the evidence lists and the provenance record.

Two values are derived rather than read from the document:

- **Rating shrinkage.** `shrunk_rating(sum, count)` returns
  `(sum + 0.5 * 2) / (count + 2)` with a confidence of `count / (count + 2)`.
  A single rating cannot move the value far from the prior. The caller shrinks
  the aggregate before it is written; the store does not shrink it on its own.
- **Mapping coverage.** `mapping_coverage(graph, tool_id)` is the share of the
  tool's mappings that the Mapper typed successfully, multiplied by
  `0.5 + 0.5 * mean confidence`. It is stored on the offering as
  `ab:mappingCoverage`, and the onboarding path computes the same number from
  the mapping result, because the unmapped fields are never written to the
  graph.

## 5. How the Client reasons over the facts

`app/agents/ranking_policy.py` holds the policy. It never calls a language
model. Ordering has two levels.

### 5.1 The tier partition is a sort key, not a factor

The commercial tier is a **partition**, applied before the score:

```text
sort key = (tier_rank, -score, tool_id)
tier_rank = position of the tier in ["free", "freemium", "paid", "unknown"]
```

A free tool is therefore always ranked above a paid one, however strong the
paid tool's raw score. A multiplier cannot express this: any finite weight can
be overcome by a sufficiently large relevance or trust value. The partition is
also why the ablation `no_tier` (`pricing_policy="ignore"`) collapses the
free-first rate from 1.0000 to 0.3542 (Section 7).

### 5.2 The score within a tier

```text
quality  = (0.4 * doc_quality + 0.3 * mapping_coverage + 0.3 * chain_fit) / 1.0
score    = relevance * trust * quality * rating_factor
```

The weights are configurable (`AB_DOC_QUALITY_WEIGHT`, `AB_MAPPING_COVERAGE_WEIGHT`,
`AB_CHAIN_FIT_WEIGHT`). `chain_fit` is the share of the tool's required inputs
that the current chain can supply, computed from the sub-goal slots and the
outputs of the upstream steps. `mapping_coverage` is the stored coverage of the
tool's mappings.

Three gates follow the score:

| Condition | Effect |
| --- | --- |
| `claim_label == "contradicted"` | `score *= contradicted_penalty` (default 0.6) |
| Provider demoted by the trust registry | `score = 0`, candidate becomes ineligible |
| Circuit breaker open on the provider link | `score = 0`, candidate becomes ineligible |

### 5.3 Rating handling

`rating_factor` is neutral unless the rating is supported by enough reviews:

```text
if rating_value is None or rating_count < min_rating_count (default 3):
    rating_factor = 1.0
else:
    rating_factor = rating_floor + (1 - rating_floor) * rating_value   # floor 0.5
```

So a rating with fewer than three reviews is ignored entirely, and a rating
can at most halve a candidate's score (a rating of 0 gives the floor of 0.5).
The floor exists so that a badly rated but well-documented tool stays visible
behind a better one instead of disappearing.

The rating itself comes from this project's own trust registry. It is never
scraped from a marketplace, a directory or a review site. The trust registry
keeps the rating aggregate per provider as `ratings_sum` and `ratings_count`;
`kg.quality.shrunk_rating()` applies the Beta prior to that aggregate, and
`KgStore.update_tool_quality()` writes the result onto the offering together
with its count and its source (`ab:ratingSource`). Nothing in this repository
wires the registry into that write yet, so the ratings in the application's
local tool catalogue are curated values rather than values read back from the
registry.

### 5.4 The executability gate

A tool may be executed only when it is free **and** keyless. `require_known_licence`
(default `False`) adds a third condition: a non-empty licence.

Everything else is still ranked and still listed:

- a paid or freemium tool keeps its place in the shortlist with the reason
  `"not executable: paid tier"` or `"not executable: freemium tier"`;
- a free tool that needs a key keeps its place with the reason
  `"not executable: requires an api key"`;
- the composition step filters the shortlist down to candidates that are both
  eligible and executable, so a non-executable candidate is never called;
- the substitution path applies the same gate to a replacement tool.

This is the mechanism behind NFR1: the project catalogues paid APIs so that a
developer can see them, but it never spends money calling them.

### 5.5 Reasons and the trace

Every candidate carries the reasons of the decision, and the Client attaches
them to the candidate in the shortlist. A top-ranked candidate records, for
example:

```text
pricing tier free
no api key required
rating 0.85 from 12 reviews
doc quality 0.85
mapping coverage 1.00
chain fit 0.90
trust 0.90
```

and a candidate that must not be called adds:

```text
not executable: requires an api key
```

The `graphrag_shortlist` trace event carries the retrieved candidates, the
filtered ones with their filter reason, the `free_first_compliance` flag, the
policy settings that were in force, and the ranked list with the tier, the
score, the eligibility, the executability and the reasons of every candidate.
The `candidate_ranking` event carries the shorter version of the same list.

## 6. What the language model may and may not do

| Task | Owner | Why |
| --- | --- | --- |
| Task decomposition and sub-goal slots | `TaskPlanner`, optional LLM | The plan is prose-level and the LLM is better at it; the deterministic planner handles the known intents |
| Concept naming and repair in the Mapper | `MapperAgent`, optional LLM | This is the LLM's extraction work; every proposal is validated deterministically before it is written |
| Prose interpretation of a specification for commercial facts | Deterministic rules | The rules are reproducible and reviewable; the LLM is not part of the commercial extraction path |
| Pricing tier, access requirement, licence, rate limit | Deterministic rules plus human overrides | These are contractual facts that a human signs off on, not model output |
| Tier order, weights, gates | `RankingPolicy` code | The arithmetic has to be deterministic and explainable (FR3, NFR4) |
| Ranking arithmetic and ordering | `RankingPolicy` code | Same reason; a model cannot be asked to reproduce a score that is audited |
| Reason text | `RankingPolicy.explain()` | The reasons must match the stored facts exactly |
| Selection and execution | `ClientAgent` | The gate is a boolean on stored facts |
| Summarising the answer | `ClientAgent` | The answer is prose and does not affect the ranking |

The practical rule: **the LLM may take part in extraction and in planning; it
may never do the ranking arithmetic.** A model output that reached the shortlist
would break both the reproducibility requirement and the requirement that a
decision be explainable from stored evidence. The optional LLM planner is not
required for the tests, the evaluation or the demonstration.

## 7. Evaluation of the ranking behaviour

The suite is `app/evaluation/run_ranking.py`:

```powershell
python -m app.evaluation.run_ranking
```

It replays a hand-checked dataset of ranking tasks through
`rank_candidates()` and writes `reports/ranking.json`. The dataset is
`app/evaluation/data/ranking_tasks.jsonl` and holds 48 tasks over the 8
curated capabilities, 6 tasks each, with 149 candidate rows over 46 distinct
tool ids. Every task has at least one free candidate.

### 7.1 The measured numbers

Command: `python -m app.evaluation.run_ranking`, dataset
`app/evaluation/data/ranking_tasks.jsonl`, default policy.

| Configuration | MRR | NDCG@10 | Free-first rate | Executable-top rate | Tier separation accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| `full` | 1.0000 | 1.0000 | 1.0000 | 0.9583 | 1.0000 |
| `no_tier` | 0.6771 | 0.8823 | 0.3542 | 0.3333 | 0.2292 |
| `no_quality` | 0.7049 | 0.9478 | 1.0000 | 0.9375 | 1.0000 |
| `no_rating` | 0.9896 | 0.9984 | 1.0000 | 0.9583 | 1.0000 |

`failures: 0` — the report's failure list (a task that is not free-first or
whose ranked order differs from the expected order) is empty.

Metric definitions:

- **MRR** is the mean reciprocal rank of the expected best tool, the first entry
  of the task's `expected_order`.
- **NDCG@10** uses graded gains: the gain of a ranked candidate is
  `len(expected_order) - position` in the expected order, so the expected best
  tool carries the largest gain. Binary gains would be 1.0 for every ranking.
- **Free-first rate** is the share of tasks that had at least one free
  candidate and whose top ranked candidate is in the free tier.
- **Executable-top rate** is the share of tasks whose top ranked candidate is
  executable, that is free and keyless under the policy in force.
- **Tier separation accuracy** is the share of tasks whose ranked list never
  places a candidate from a lower tier above a candidate from a higher tier.

### 7.2 What the ablations show

- **Without the tier partition** (`no_tier`) the free-first rate falls from
  1.0000 to 0.3542, the executable-top rate from 0.9583 to 0.3333 and the tier
  separation accuracy from 1.0000 to 0.2292. The policy still finds the right
  tool more often than not (MRR 0.6771), but it puts paid and keyed tools on
  top, which is exactly what the project must not do.
- **Without the quality factors** (`no_quality`) the MRR falls from 1.0000 to
  0.7049 and the NDCG@10 from 1.0000 to 0.9478, while the free-first rate
  stays at 1.0000. The tier partition and the quality factors are separate
  mechanisms and both carry weight.
- **Without the rating** (`no_rating`, `min_rating_count` raised so the factor
  is always neutral) the MRR falls slightly to 0.9896 and the NDCG@10 to
  0.9984. On this dataset the rating is a small effect: 34 of the 149
  candidate rows carry fewer than three reviews and are ignored by the default
  policy anyway.

### 7.3 Why the executable-top rate is not 1.0

Two tasks have a free but keyed candidate at the top of the free tier, and the
policy ranks it first because it has the highest score inside that tier:

| Capability | Task | Top candidate | Score | Reason |
| --- | --- | --- | ---: | --- |
| `GetWeatherForecast` | What is the weekend temperature in Berlin? | `key-required-weather-pro` | 0.718029 | `pricing tier free`, `requires api key` |
| `QueryStructuredData` | How many students are enrolled in the university database? | `campus-sql-cloud-tier` | 0.636291 | `pricing tier free`, `requires api key` |

The second task also shows the partition at work: the paid `keyed-sql-cloud`
has a higher raw score (0.643245) than the free `university-sql` (0.3668) and
still ranks last.

Both tasks keep the expected order (the dataset was written that way), and both
top candidates are recorded as not executable. The Client would skip them and
continue down the shortlist. 46 of 48 tasks have an executable top candidate,
which is the 0.9583 in the table.

The dataset is hand-written, so these numbers describe the policy on a
curated set of 48 tasks. They are not a claim about live internet behaviour;
see the threats to validity in
[evaluation-plan.md](evaluation-plan.md#11-ranking-evaluation-free-first-ranking).

## 8. Known limits

- **Most of the corpus has an unknown tier.** Of the 98 corpus documents, 89
  are `unknown`, 7 are `free` and 2 are `freemium`; none is classified `paid`.
  The corpus documents are mostly API descriptions that do not discuss pricing
  at all, which is exactly the case the rules refuse to guess about. In the
  tier partition these tools sit last, behind every classified tool.
- **Most of the corpus needs a key.** 85 of the 98 documents are `api_key`,
  2 are `paid_key` and 11 are `keyless`. Only 11 tools can be probed live.
- **The probe set is one tool short.** The proposal asks for 12 to 15 keyless
  APIs; the corpus yields 11. No extraction rule can close the gap; the corpus
  needs another keyless document.
- **Ratings are cold in the corpus.** The 98 corpus documents carry no rating:
  the corpus manifest has no rating field, and the committed
  `data/out/graph.ttl` was built before the offering extension, so it holds no
  offering node. The application's local tool catalogue does carry curated
  ratings for its 9 providers (`nominatim-geocode` at 0.88 from 31 reviews,
  `mock-weather-fahrenheit` at 0.20 from 4), so the rating factor is engaged in
  the application; for the corpus tools it is neutral everywhere and the policy
  ranks on relevance, trust, quality and tier alone.
- **No licence has been signed off.** Every entry in
  `data/overrides/pricing.yaml` has an empty `reviewer`, so
  `licence_reviewed_at` is empty throughout the manifest. The licence and
  terms facts are recorded, not approved.
- **The knowledge-layer executability check does not require a licence by
  default.** `kg.quality.is_executable()` and the `executable_tools()` query
  treat a free keyless tool as executable even when its licence is unknown,
  because `require_known_licence` defaults to `False`; the Client policy has
  the same default, but the query's own docstring says "free, keyless and with
  a known licence". The two readings differ, and
  `tests/test_kg_quality.py::test_executable_tools_lists_only_free_keyless_tools`
  fails on the current checkout because it expects the stricter reading.
  Aligning the query with its docstring, or the docstring with the code, is
  an open decision; the documentation here states the code's behaviour.
- **The pricing tier is a partition, so a wrongly classified tool is badly
  placed.** A free tool classified as `unknown` sits behind every classified
  tool; a paid tool misread as free would be executed. The curated override
  file is the mitigation, and it is not yet reviewed.

## 9. Extension points

- **New sources.** Implement the `SpecSource` protocol and pass it to
  `fetch_specs.py`; the protocol is the only contract the corpus builder
  needs. A source that wants to be selected by the seed rule only has to
  provide `access_requirement` and `pricing_tier` on its candidate entries.
- **New commercial facts.** Add a field to `ListingMetadata`, a predicate to
  `ab:Offering` and its shape constraint, and a column to the manifest entry.
  An override may only set the fields that `apply_override()` copies, so a new
  overridable field has to be added to that list as well.
- **Different pricing policies.** `pricing_policy` accepts `prefer_free` and
  `ignore`; `tier_order` is configurable, and `unknown` is always appended if
  it is missing. A policy that prefers the cheapest tool would need a new
  branch in `tier_rank` and a new ablation in the suite.
- **Different quality weights.** The three weights are settings and are read
  from the environment, so an experiment can be run without a code change.
- **A second gate on the licence.** `require_known_licence` already exists and
  is read from the settings; only the knowledge-layer query disagrees with it.
- **Live probe execution.** `probe_budget_per_minute` is extracted and stored
  per tool, which is the input a live prober needs to respect the provider's
  limit. The probe runner itself is not implemented.
- **A rating source.** `ab:ratingSource` and `update_tool_quality(rating_source=...)`
  exist so that a rating can be attributed. The trust registry is the intended
  source, but nothing writes its rating aggregate into the offering yet.

## References

- Sources: `src/agent_bazaar/ingestion/sources.py`
- Extraction rules: `src/agent_bazaar/ingestion/listing_metadata.py`
- Corpus build, manifest v2 and refresh: `scripts/fetch_specs.py`
- Curated overrides: `data/overrides/pricing.yaml`
- Probe set: `data/specs/probe_set.json`
- Quality profile and offering triples: `src/agent_bazaar/kg/quality.py`
- Store and write path: `src/agent_bazaar/kg/store.py`
- Ontology and shapes: `src/agent_bazaar/ontology/upper.ttl`,
  `src/agent_bazaar/ontology/shapes.ttl`
- Ranking policy: `app/agents/ranking_policy.py`
- Client integration: `app/agents/client.py`
- Settings: `app/config.py`
- Evaluation: `app/evaluation/run_ranking.py`,
  `app/evaluation/data/ranking_tasks.jsonl`
- Corpus provenance: [`../data/specs/README.md`](../data/specs/README.md)
- Graph schema: [graph-schema.md](graph-schema.md)
- Decisions: [decisions.md](decisions.md)
- Evaluation plan: [evaluation-plan.md](evaluation-plan.md)
