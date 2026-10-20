# Agent Bazaar

A marketplace where agents map, find, verify, chain and learn to trust third-party services.

Ontology- and knowledge-graph-driven multi-agent system, BS Artificial Intelligence,
University of Central Punjab.

## Documentation

- [Week 1 scope and shared protocol](docs/week1-scope-and-protocol.md)
- [Ontology, units and SHACL](docs/ontology.md)
- [Graph schema and queries](docs/graph-schema.md)
- [Mapper protocol](docs/mapper-protocol.md)
- [Onboarding guide](docs/onboarding.md)
- [Decisions and known limitations](docs/decisions.md)
- [Evaluation plan](docs/evaluation-plan.md)
- [Specification corpus provenance](data/specs/README.md)

## Team branches

- `maria` - knowledge layer and Mapper lead (ontology, knowledge graph, vector index, ingestion utility, Mapper agent, mapping evaluation)
- `qaim` - Auditor and monitoring lead
- `rameen` - Client, Provider and interface lead

## Quickstart (PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# Deterministic, offline path
python scripts/build_ontology.py --offline
python scripts/seed_graph.py --offline --hash-embeddings
python scripts/demo_mapper.py
python -m pytest
```

This uses the committed 8-spec seed corpus and the deterministic hashing
embedder. No API key is needed. To fetch the full corpus and use the embedding
model:

```powershell
python -m pip install -e ".[dev,embeddings]"
python scripts/fetch_specs.py --limit 100
python scripts/build_ontology.py --offline

# Optional: onboard the full corpus instead of the 8 seed specs (slower; overwrites graph.ttl)
python scripts/seed_graph.py --offline --specs data\specs
```

For LLM ontology generation or LLM mapping, copy the example settings and export a
key in the current shell:

```powershell
Copy-Item config\settings.example.yaml config\settings.yaml
$env:GROQ_API_KEY = "..."     # example config default; Gemini/OpenRouter also supported
```

`config/settings.yaml` is gitignored. Secrets are read from environment variables;
nothing secret is written to the repository. The code does not load a `.env` file
automatically.

Current artifacts: 8 seed tools, 60 ontology concepts, 512 mapping results
(467 distinct graph mapping nodes), 449 unmapped fields, and 89 passing tests.
The graph is built from the 8 seed specs, not all 98 corpus specs. The 916-row
mapping evaluation template also covers the 8 seed tools and has no gold labels
yet, so this repository makes no accuracy or F1 claim. The committed specs are
third-party documents with mixed declared licenses; check
[the corpus note](data/specs/README.md#licensing) before redistributing them.

## Repository layout

```
src/agent_bazaar/
  messages/     structured JSON message schemas (protocol)
  ontology/     upper ontology, units, SHACL shapes, domain layer and generator
  kg/           RDF knowledge graph store, loader and query helpers
  vec/          vector index (ontology terms, tool descriptions, corrections)
  ingestion/    OpenAPI, PDF, DOCX and text ingestion utility
  mapper/       Mapper agent: retrieval, LLM mapping, SHACL repair, staging, drift
  evaluation/   mapping metrics, ablations and learning-curve helpers
  llm/          cached chat-completions client
  pipeline.py   listing -> ingestion -> mapping -> validated graph write
docs/           scope, protocol, ontology, graph, Mapper, onboarding, decisions, evaluation
scripts/        corpus fetch, ontology build, graph seed, demo and evaluation entry points
tests/          89 unit and end-to-end tests
data/
  specs/        generated corpus; committed 8-spec seed subset, seed manifest and README
  out/          committed ontology.ttl, graph.ttl and build/seed logs
  eval/         committed 916-row unlabelled mapping template
  vectors/      generated vector index (not committed)
  memory/       generated correction memory (not committed)
  staging/      generated correction staging log (not committed)
  cache/        generated LLM cache (not committed)
  demo/         generated demo workspace from scripts/demo_mapper.py
config/         settings.example.yaml; settings.yaml is gitignored
```

Committed artifacts: `data/out/ontology.ttl` (upper + units + 60 concepts),
`data/out/graph.ttl` (8 tools, 467 mapping nodes), `data/out/logs/` build
summaries, `data/eval/mapping_gold.jsonl`, the 8-spec seed corpus, and the
documents under `docs/`.

The Mapper writes validated mappings and uses a bounded repair loop; corrections
are staged before promotion. See the Mapper protocol and decisions documents for
current limitations, including the difference between 512 mapping results and
467 distinct mapping nodes.
