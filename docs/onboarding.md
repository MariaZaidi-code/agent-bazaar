# Onboarding guide

This guide takes a new team member from a clean checkout to a mapped, validated
knowledge graph, then shows how to onboard one API and how to diagnose failures.
It assumes Windows PowerShell; commands are equivalent on other shells.

## 1. Prerequisites

- Git.
- Python 3.10 or newer (3.11 is the development target).
- No API key is needed for the offline path.
- An API key is needed only for LLM ontology generation or LLM mapping. The
  example configuration uses Groq; if your local configuration selects Gemini,
  `GEMINI_API_KEY` must be present in the process environment.

Check Python and Git:

```powershell
git --version
python --version
```

If `python` is not on PATH, use `py -3.11` in place of `python`.

## 2. Get the repository

```powershell
git clone <repository-url> agent-bazaar
Set-Location agent-bazaar
git switch maria
```

The branch contains the knowledge layer and Mapper. The committed seed corpus is
under `data/specs/seed`; generated specs, vectors, memory, staging, and model
cache are ignored by Git.

## 3. Install

Create an isolated environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

If PowerShell blocks activation:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

Choose one install:

```powershell
# Offline/core + tests: enough for every command below with --hash-embeddings
python -m pip install -e ".[dev]"

# Full embedding model (downloads sentence-transformers and its runtime)
python -m pip install -e ".[dev,embeddings]"
```

`requirements.txt` is also available and includes `sentence-transformers` and
`pytest`. The core install is enough for the deterministic hash-embedding path;
`sentence-transformers` is optional and can be large on Windows.

## 4. Configure

Defaults are in code. To override them:

```powershell
Copy-Item config\settings.example.yaml config\settings.yaml
```

`config/settings.yaml` is gitignored. Do not put secrets in it.

For an LLM run, set the key for the provider you selected in the current
PowerShell session:

```powershell
$env:GROQ_API_KEY = "..."      # example config default
# $env:GEMINI_API_KEY = "..."  # if settings.yaml selects gemini
```

Alternatively use `OPENROUTER_API_KEY` and select the matching provider in
`config/settings.yaml`. The code reads `os.environ`; copying
`.env.example` to `.env` does **not** load it automatically. Export the variable,
use a dotenv loader, or configure the key in your process manager.

## 5. Build the offline artifacts

Run from the repository root, in this order:

```powershell
python scripts/build_ontology.py --offline
python scripts/seed_graph.py --offline --hash-embeddings
```

What each does:

- `build_ontology.py --offline` scans the 98 JSON specifications in
  `data/specs` (excluding `manifest.json`), uses the curated 60-concept seed
  layer, validates it, and writes `data/out/ontology.ttl`, `data/out/domain.ttl`,
  and `data/out/logs/ontology_build.json`.
- `seed_graph.py --offline --hash-embeddings` reads the 8 seed specs in
  `data/specs/seed`, maps them with the heuristic mapper, writes and validates
  `data/out/graph.ttl`, and persists vectors under `data/vectors`.
  `--offline` disables the LLM; `--hash-embeddings` forces the deterministic
  embedder.

Expected successful output (current committed seed):

| Item | Value |
| --- | --- |
| Ontology source | `seed` |
| Concepts | 60 |
| Ontology violations | 0 |
| Seed specifications | 8 |
| Tools written | 8 |
| Mapper mapping results | 512 |
| Unmapped fields | 449 |
| Distinct graph mappings | 467 |
| Graph claims | 0 |
| Ontology-term vectors | 60 |
| Tool-description vectors | 8 |
| Correction vectors | 0 |

512 mapping results become 467 graph nodes because mapping identity is a hash of
tool, field path, and direction. See [graph-schema.md](graph-schema.md#mapping-identity-and-collisions).

The build summary is authoritative for the run you just made. The number of
uncovered fields and any LLM batch counts change with the corpus, model, and
`--limit-specs`; do not copy stale values from an older log. In particular, a
small review run overwrites `data/out/logs/ontology_build.json` and
`data/out/ontology.ttl`, so re-run the full offline build before quoting totals.

## 6. Verify the install

```powershell
python -m pytest
```

Expected: `89 passed`. The suite covers messages, ingestion, ontology generation,
units, validation, graph store and queries, vectors, Mapper rules/repair/staging,
evaluation metrics, and the end-to-end seed path.

Check the artifacts directly:

```powershell
python -c "from agent_bazaar.kg import KgStore; s=KgStore.build_default(); print(s.describe_graph()); print('conforms:', s.validate().conforms)"

python -c "from agent_bazaar.vec import VectorService; v=VectorService.load_or_create(force_fallback=True); print({c: v.count(c) for c in ('ontology_terms','tool_descriptions','corrections')})"
```

Expected graph dictionary:
`{'tools': 8, 'concepts': 60, 'mappings': 467, 'claims': 0}` and
`conforms: True`. Expected vector counts:
`{'ontology_terms': 60, 'tool_descriptions': 8, 'corrections': 0}`.

If `VectorService.load_or_create()` reports a dimension mismatch, the persisted
index was built with a different embedder. Delete the generated
`data/vectors` directory and rebuild with one consistent mode:

```powershell
Remove-Item -Recurse -Force data\vectors
python scripts/seed_graph.py --offline --hash-embeddings
```

Do not mix a sentence-transformer run (384-dimensional model by default) with a
different embedding model without rebuilding; drift distances are not comparable
across models.

## 7. Run the offline Mapper demonstration

```powershell
python scripts/demo_mapper.py
```

It prints a mapping table, a promoted and a rejected correction, a drift re-map,
and graph/vector counts. It uses the repository ontology if
`data/out/ontology.ttl` exists (otherwise the curated seed), writes demo memory
and staging under `data/demo`, and does not save `data/out/graph.ttl` or persist
vectors.

`data/out/logs/demo_mapper.txt` is a captured transcript, not a file the demo
creates. The committed copy is partial: it holds only the first line
(`demo workspace: ...`), so do not quote it as the demo output. To capture a
fresh transcript, redirect both streams (the structured Mapper log goes to
stderr, the tables go to stdout):

```powershell
python scripts/demo_mapper.py *> data\out\logs\demo_mapper_new.txt
```

To capture stdout only:

```powershell
python scripts/demo_mapper.py > data\out\logs\demo_mapper_new.txt
```

## 8. Onboard one listing

### Through the seed script

For a directory of OpenAPI files, the supported batch path is:

```powershell
python scripts/seed_graph.py --offline --hash-embeddings --specs data/specs/seed --limit 1
```

This rebuilds `data/out/graph.ttl` from scratch (`load_existing=False`), writes
only the selected tool(s), and overwrites the persisted vector index. It is a
rebuild command, not an incremental add. Use the Python API below for an
incremental onboarding.

### Through the Python API

After `pip install -e .`, create `onboard_one.py` outside the package (or run the
same code in a notebook):

```python
from pathlib import Path

from agent_bazaar.config import ensure_directories, get_settings
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.pipeline import onboard_spec
from agent_bazaar.vec import VectorService

settings = ensure_directories()
store = KgStore.build_default(load_existing=True)
vector = VectorService.load_or_create(settings=settings, force_fallback=True)
mapper = MapperAgent(
    store,
    vector,
    client=None,                 # LLM: pass build_llm_client() and use_llm=True
    ingester=IngestionUtility(settings.ingestion),
    settings=settings,
    use_llm=False,
)

spec = IngestionUtility(settings.ingestion).ingest(Path("path/to/spec.json"))
outcome = onboard_spec(
    spec,
    mapper,
    store,
    vector=vector,
    write=True,
    tool_id="my-tool",           # omit to use the filename stem
)
print("written:", outcome.written, "error:", outcome.error)
print("mapped:", outcome.result.stats.get("mapped"))
print("unmapped:", [f.field_path for f in outcome.result.unmapped])

if outcome.written:
    store.save()
    vector.persist()
```

Run it with `python onboard_one.py`. To use the LLM path:

```python
from agent_bazaar.llm.client import build_llm_client

client = build_llm_client()
mapper = MapperAgent(
    store, vector, client=client, ingester=IngestionUtility(settings.ingestion),
    settings=settings, use_llm=True,
)
```

Set the provider key first. The first run writes JSON responses to
`data/cache/llm`; later identical prompts replay from cache. When the key is
missing or the provider is `offline`, mapping falls back to the heuristic.

Important side effects:

- Mapping writes individual mappings before the tool is written. If
  `outcome.written` is false, the in-memory graph may already contain mappings;
  the script above only saves on success, so on-disk state is unchanged. Do not
  save after a failed write without inspecting the graph.
- A tool needs at least one mapped output. If all output fields are unmapped,
  `ToolShape` rejects the write and `outcome.error` explains the violation.
- The mapping result may include `status="unmapped"` records; filter them before
  using mappings as successes.
- Provider metadata on `ListingSubmit` is not used by `handle_listing_submit`;
  the Python onboarding path derives the provider from the spec.

See [mapper-protocol.md](mapper-protocol.md) for statuses, repair, corrections,
and known gaps.

## 9. Fetch or refresh the corpus

```powershell
python scripts/fetch_specs.py --limit 100
```

The script:

- reads the APIs.guru list;
- uses seed 42 and a deterministic selection;
- skips documents larger than 1.5 MB or not recognizable as OpenAPI;
- writes `data/specs/manifest.json` and copies the 8 seed specs to
  `data/specs/seed`;
- prints the number skipped (currently 2) but does **not** store skip reasons in
  the manifest.

Do not edit the corpus manifest by hand. If the upstream list changes, record the
new counts and the retrieval date. Existing files are reused unless `--force` is
given; the manifest is rewritten from the current selection.

## 10. Build with an LLM (optional)

```powershell
$env:GROQ_API_KEY = "..."      # example config default; use GEMINI_API_KEY if configured
python scripts/build_ontology.py
```

Without a key, the script prints a warning and uses the curated seed layer. With
a key, it inventories uncovered fields, batches them (default 40), caches every
call, validates the merged ontology, and permits two repair rounds. Check:

- the `source` in `data/out/logs/ontology_build.json` (`seed` for the offline
  fallback, `mixed` when accepted LLM concepts were merged with the seed);
- `violations_found` and `violations_fixed`;
- `failed_batches`;
- `data/out/logs/ontology_violations.jsonl` for round-by-round problems;
- the concept list before committing `data/out/ontology.ttl`.

For a quick review, use `--limit-specs 3`. This intentionally produces a smaller
ontology and a small inventory summary; do not treat that artifact as the full
build. Re-run the full command before seeding the graph.

## 11. Troubleshooting

| Symptom | Cause | Fix |
| --- | --- | --- |
| `no specs found` | corpus missing/empty | run `fetch_specs.py` or use `data/specs/seed` |
| `store has no concepts` | ontology artifact absent or empty | run `build_ontology.py --offline` |
| `missing API key` | key not in the process environment | export the key or use offline mode |
| `.env` exists but key is missing | code does not load `.env` | export the provider's key or load dotenv yourself |
| LLM calls fail or time out | quota, network, or endpoint issue | use `--offline`/heuristic; cached prompts still replay |
| sentence-transformers download fails | no model cache/network | install `.[embeddings]` or use `--hash-embeddings` |
| persisted vector dimension mismatch | embedder changed | delete `data/vectors` and rebuild consistently |
| graph has no tools / `written=False` | no outputs mapped, shape violation, or write error | inspect `outcome.error` and `outcome.result.unmapped`; ensure an output field maps |
| `conforms: False` | invalid graph or stale artifact | inspect `s.validate().violations`; rebuild ontology then graph |
| 512 vs 467 mismatch | mapping IRI collapse | expected; report both values |
| two `ab:recordedAt` values | onboarding maps then writes the tool; both add a timestamp | expected in the seed artifact; do not read it as two events |
| no `demo_mapper.txt` update | demo prints, does not write a log | redirect output yourself (`*>` for stdout+stderr) |
| PowerShell activation blocked | execution policy | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass` |
| `python` not found | not on PATH | use `py -3.11` or the venv interpreter |

## 12. Clean rebuild and reset

Generated state can be removed safely; source and the seed corpus cannot.

```powershell
Remove-Item -Recurse -Force data\out, data\vectors, data\memory, data\staging, data\cache -ErrorAction SilentlyContinue
python scripts/build_ontology.py --offline
python scripts/seed_graph.py --offline --hash-embeddings
python -m pytest
```

`data/specs` is partially ignored: the committed seed is tracked, while the full
corpus and manifest are generated. Do not remove `data/specs/seed` or
`data/specs/README.md`.

## 13. Where to go next

- Scope and protocol: [week1-scope-and-protocol.md](week1-scope-and-protocol.md)
- Ontology and units: [ontology.md](ontology.md)
- Graph schema and queries: [graph-schema.md](graph-schema.md)
- Mapper behaviour: [mapper-protocol.md](mapper-protocol.md)
- Decisions and limitations: [decisions.md](decisions.md)
- Evaluation plan: [evaluation-plan.md](evaluation-plan.md)
- Corpus provenance: [`../data/specs/README.md`](../data/specs/README.md)
