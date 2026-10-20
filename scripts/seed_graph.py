"""Onboard specs end to end: ingest, map to the ontology, write the RDF graph.

Use --offline for the deterministic heuristic mapper (no network); with an API
key present the LLM mapper is used with the prompt cache.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import _bootstrap  # noqa: F401
from agent_bazaar.config import ensure_directories, get_settings
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore, describe_graph
from agent_bazaar.llm.client import build_llm_client
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.pipeline import OnboardOutcome, onboard_spec, tool_id_for_spec
from agent_bazaar.vec import build_vector_service


def build_mapper(store: KgStore, vector, offline: bool, settings) -> MapperAgent:
    client = None
    if not offline:
        try:
            client = build_llm_client()
        except Exception as exc:
            print(f"warning: LLM unavailable ({exc}); using the heuristic mapper")
    return MapperAgent(
        store,
        vector,
        client=client,
        ingester=IngestionUtility(settings.ingestion),
        settings=settings,
        use_llm=client is not None,
    )


def main() -> int:
    settings = ensure_directories()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", type=Path, default=settings.paths.specs_dir / "seed")
    parser.add_argument("--graph", type=Path, default=settings.paths.graph_path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--hash-embeddings", action="store_true", help="force the deterministic hashing embedder")
    args = parser.parse_args()

    store = KgStore.build_default(load_existing=False)
    if not store.list_concepts():
        print("store has no concepts; build the ontology first (scripts/build_ontology.py --offline works)")
        return 1
    vector = build_vector_service(settings, force_fallback=args.hash_embeddings)
    mapper = build_mapper(store, vector, args.offline, settings)
    mapper.build_index()

    results: list[OnboardOutcome] = []
    failures: list[dict] = []
    files = sorted(p for p in args.specs.glob("*.json") if p.name != "manifest.json")
    if args.limit:
        files = files[: args.limit]
    known_ids: set[str] = set()
    for path in files:
        try:
            spec = mapper.ingester.ingest(path)
        except Exception as exc:
            failures.append({"file": path.name, "error": f"ingestion: {exc}"})
            continue
        tool_id = tool_id_for_spec(spec, known_ids)
        known_ids.add(tool_id)
        outcome = onboard_spec(spec, mapper, store, vector=vector, write=True, tool_id=tool_id)
        results.append(outcome)
        if not outcome.written:
            failures.append({"file": path.name, "tool_id": tool_id, "error": outcome.error})

    saved = store.save(args.graph)
    vector.persist(settings.paths.vectors_dir)

    total_mappings = sum(len(result.result.mappings) for result in results)
    total_unmapped = sum(len(result.result.unmapped) for result in results)
    stats = describe_graph(store.graph)
    report = {
        "specs": len(files),
        "tools_written": sum(1 for r in results if r.written),
        "mappings": total_mappings,
        "unmapped_fields": total_unmapped,
        "failures": failures,
        "graph": stats,
        "graph_path": str(saved),
        "vector_counts": {"ontology_terms": vector.count("ontology_terms")},
    }
    log_dir = settings.paths.out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / "seed_graph.json").write_text(json.dumps(report, indent=1), encoding="utf-8")

    print("\n| item | value |")
    print("| --- | --- |")
    for key in ("specs", "tools_written", "mappings", "unmapped_fields"):
        print(f"| {key} | {report[key]} |")
    for key, value in stats.items():
        print(f"| graph.{key} | {value} |")
    if failures:
        print(f"\n{len(failures)} failures (see data/out/logs/seed_graph.json)")
    print(f"\ngraph written to {saved}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
