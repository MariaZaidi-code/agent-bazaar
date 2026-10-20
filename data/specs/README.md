# Specification corpus

This directory holds the OpenAPI corpus used to build the ontology and the seed
knowledge graph. The full corpus and its manifest are generated and ignored by
Git; the 8-spec seed subset and `seed/manifest.json` are committed for offline
reproduction.

Counts below were observed on 2026-10-20. They describe the current checkout, not
a permanent upstream guarantee.

## Layout

| Path | State | Contents |
| --- | --- | --- |
| `manifest.json` | Generated, ignored | 98 selected corpus entries with key, title, categories, provider, version, upstream URL, file, bytes, status |
| `*.json` | Generated, ignored | One downloaded OpenAPI document per manifest entry |
| `seed/manifest.json` | Committed | 8 seed entries copied from the corpus manifest |
| `seed/*.json` | Committed | The 8 offline seed documents |
| `README.md` | Committed | This provenance and licensing note |

`data/specs/` holds 99 JSON files at the top level: the 98 specification
documents plus `manifest.json`. The `seed/` subdirectory holds 9 more (8
documents plus its own manifest), and this `README.md` sits beside them. The
corpus totals 8,516,553 bytes; the seed totals 406,909 bytes. The largest single
corpus document is 462,372 bytes (`impala-travel-hotels.json`).

## How the corpus was fetched

`scripts/fetch_specs.py`:

1. Downloads the APIs.guru directory from
   `https://api.apis.guru/v2/list.json`.
2. Keeps the preferred version's `swaggerUrl` for each API and records its title,
   categories, provider, version, and URL.
3. Sorts candidates by API key, selects with `random.Random(42)` using
   `--limit 100`: half from priority categories (`weather`, `location`,
   `geocoding`, `maps`, `currency`, `finance`, `government`, `open_data`,
   `data`, `geography`) and the rest from the remainder.
4. Rejects documents larger than 1,500,000 bytes or without an `openapi`/
   `swagger` marker in the first 2000 characters.
5. Writes the manifest and copies 8 seed documents to `seed/`.

The current run selected 100 candidates, skipped 2, and produced 98 specifications:

```text
corpus: 98 specs in data/specs (2 skipped)
seed corpus: 8 specs in data/specs/seed
```

Only the number of skips is printed to stdout; the two skip reasons are neither
stored in `manifest.json` nor printed, which is a reproducibility gap. The
manifest records only successful selections (`status` is `existing` for files
reused on this run).

Existing files are reused unless `--force` is passed. The manifest is rewritten
from the current selection even when files are reused, so a later upstream change
can change selection metadata without changing the local documents.

## Seed corpus

The seed is deterministic but not random. `fetch_specs.py` first tries
`SEED_PREFERRED_FILES`, keeps only documents with at least one output field, then
ranks the rest by demo keywords and size. It copies the chosen files and removes
stale seed documents. The default is `--seed-files 8`. `Document version` below
is `info.version` from the document; the APIs.guru key version can differ.

| Tool id (file stem) | File | API key | Document version | Bytes | Categories | License declared in document |
| --- | --- | --- | --- | --- | --- | --- |
| `citycontext-com` | `citycontext-com.json` | `citycontext.com` | 1.0.0 | 10,579 | open_data | none |
| `gisgraphy-com` | `gisgraphy-com.json` | `gisgraphy.com` | 4.0.0 | 66,855 | location | "LGPL license V3." |
| `ideal-postcodes-co-uk` | `ideal-postcodes-co-uk.json` | `ideal-postcodes.co.uk` | 3.7.0 | 282,716 | location | AGPLv3 |
| `interzoid-com-getzipinfo` | `interzoid-com-getzipinfo.json` | `interzoid.com:getzipinfo` | 1.0.0 | 4,807 | developer_tools | Interzoid license |
| `miataru-com` | `miataru-com.json` | `miataru.com` | 1.0.0 | 18,736 | location | Public Domain |
| `nytimes-com-geo-api` | `nytimes-com-geo-api.json` | `nytimes.com:geo_api` | 1.0.0 | 8,287 | media, open_data | none |
| `iptwist-com` | `iptwist-com.json` | `iptwist.com` | 1.0.0 | 3,196 | developer_tools | none (terms URL only) |
| `deutschebahn-com-fahrplan` | `deutschebahn-com-fahrplan.json` | `deutschebahn.com:fahrplan` | v1 | 11,733 | transport, open_data | DB Data Portal |

Tool ids are derived from the file stem by `IngestionUtility.ingest`, not from
the dotted APIs.guru key. For example, `deutschebahn.com:fahrplan` becomes
`deutschebahn-com-fahrplan` in the graph. This is why the seed graph tool ids are
lower-case, hyphenated file names.

The seed intentionally covers location, postal/geocoding, open data, transport,
and general reference. It does not cover every ontology domain; weather and
currency concepts exist in the ontology but the current 8 seed tools are not a
balanced sample of those domains. Do not treat seed accuracy as full-corpus
coverage.

## Upstream provenance

APIs.guru versions and upstream URLs recorded in `seed/manifest.json`:

| File | Upstream specification URL |
| --- | --- |
| `citycontext-com.json` | `https://api.apis.guru/v2/specs/citycontext.com/1.0.0/swagger.json` |
| `gisgraphy-com.json` | `https://api.apis.guru/v2/specs/gisgraphy.com/4.0.0/swagger.json` |
| `ideal-postcodes-co-uk.json` | `https://api.apis.guru/v2/specs/ideal-postcodes.co.uk/3.7.0/openapi.json` |
| `interzoid-com-getzipinfo.json` | `https://api.apis.guru/v2/specs/interzoid.com/getzipinfo/1.0.0/openapi.json` |
| `miataru-com.json` | `https://api.apis.guru/v2/specs/miataru.com/1.0.0/swagger.json` |
| `nytimes-com-geo-api.json` | `https://api.apis.guru/v2/specs/nytimes.com/geo_api/1.0.0/openapi.json` |
| `iptwist-com.json` | `https://api.apis.guru/v2/specs/iptwist.com/1.0.0/openapi.json` |
| `deutschebahn-com-fahrplan.json` | `https://api.apis.guru/v2/specs/deutschebahn.com/fahrplan/v1/swagger.json` |

The manifest's `version` is the APIs.guru `openapiVer` when available, so it can
differ from the `info.version` inside the document (`citycontext` is an example).
The URL and file are the authoritative pair for provenance.

## Licensing

These are third-party API descriptions, not original Agent Bazaar content. The
manifest does not record a license field; license declarations and terms URLs, when
present, are inside each document. In the eight committed seed documents:

- five declare `info.license`: DB Data Portal, LGPL v3, AGPLv3, Interzoid license,
  and Public Domain;
- three declare none: `citycontext-com`, `nytimes-com-geo-api`, and `iptwist-com`.
  `iptwist-com` and `nytimes-com-geo-api` still carry an
  `info.termsOfService` URL; `citycontext-com` declares neither.

Those declarations are provider metadata, not a legal review. AGPL/LGPL and custom
provider terms can restrict redistribution or derived use. Do not assume a document
is public domain or open source merely because it is accessible. Before
redistributing the corpus, publishing a derived artifact, or using a service
commercially:

1. check the upstream provider's terms and the license in the document, if any;
2. preserve attribution and any copyright notice;
3. remove documents whose terms do not permit the intended use. For a public
   release, consider shipping the fetch script and manifest URLs instead of the
   third-party documents, unless permission to redistribute is confirmed.

The repository does not grant a license to the third-party specifications. The
code's license, if any, is separate from the corpus. API keys and access tokens
must not be added to this directory; the documents should be unauthenticated
specifications, not captured credentials.

## Reproducing the corpus

From the repository root:

```powershell
python scripts/fetch_specs.py --limit 100
python scripts/build_ontology.py --offline
python scripts/seed_graph.py --offline --hash-embeddings
```

To regenerate the 8-spec seed from the current corpus only:

```powershell
python scripts/fetch_specs.py --limit 100 --seed-files 8
```

To force re-download (selection and upstream content may change):

```powershell
python scripts/fetch_specs.py --limit 100 --force
```

Record the date, the corpus manifest, and the Git commit when reporting results.
The full corpus is deliberately not committed; the committed seed and its
manifest are the reviewable snapshot. Deleting `data/specs/*.json` (except
`seed/`) is safe if you can re-fetch; deleting `data/specs/seed` removes the
offline demo corpus.

## Known limitations

- Two fetch skips are not persisted with reasons.
- Upstream content can change; existing files are reused, so a local corpus is a
  historical snapshot, not necessarily today's APIs.guru state.
- The 98-file corpus includes very large and very small APIs; field counts are
  uneven and the seed is biased toward geocoding/open data.
- PDF/DOCX ingestion is implemented for documents, but this corpus is entirely
  JSON OpenAPI.
- The seed was chosen for demo relevance and output availability, not by a
  stratified random sample. Do not use it to estimate full-corpus performance.
- The manifest's `provider` field is often empty even when an upstream provider
  exists; tool/provider metadata therefore falls back to other fields.

## Related documentation

- Corpus fetch script: `scripts/fetch_specs.py`
- Ingestion and field paths: `src/agent_bazaar/ingestion/`
- Ontology build: `docs/ontology.md`
- Graph and seed counts: `docs/graph-schema.md`
- Onboarding: `docs/onboarding.md`
- Evaluation: `docs/evaluation-plan.md`
