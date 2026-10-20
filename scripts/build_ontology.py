"""Generate and validate the domain ontology layer from the spec corpus.

Runs the LLM generation + SHACL repair loop (cached), then writes the frozen
ontology artifact (upper + units + domain) and a violation log for the report.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

import _bootstrap  # noqa: F401
from agent_bazaar.config import Settings, ensure_directories, get_settings
from agent_bazaar.ingestion.models import flatten_fields
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.llm.client import LLMError, build_llm_client
from agent_bazaar.ontology.domain import concepts_to_graph, save_concepts
from agent_bazaar.ontology.generator import generate_domain_layer
from agent_bazaar.ontology.upper import load_upper
from agent_bazaar.ontology.units import units_graph
from agent_bazaar.ontology.validator import validate_graph


def field_inventory(specs_dir: Path, limit: int, settings: Settings) -> tuple[list[dict], dict]:
    utility = IngestionUtility(settings.ingestion)
    samples: list[dict] = []
    stats = {"specs": 0, "errors": 0, "fields": 0}
    files = sorted(p for p in specs_dir.glob("*.json") if p.name != "manifest.json")
    if limit:
        files = files[:limit]
    for path in files:
        try:
            spec = utility.ingest(path)
        except Exception:
            stats["errors"] += 1
            continue
        stats["specs"] += 1
        for field in flatten_fields(spec):
            samples.append(
                {
                    "field_name": field.path.rsplit(".", 1)[-1],
                    "type": field.type,
                    "description": field.description,
                    "tool_id": spec.tool_id,
                }
            )
    stats["fields"] = len(samples)
    return samples, stats


def build_client(offline: bool):
    if offline:
        return None
    client = build_llm_client()
    env_name = {"groq": "GROQ_API_KEY", "gemini": "GEMINI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}.get(
        client.provider, ""
    )
    if env_name and not os.environ.get(env_name):
        print(f"warning: {env_name} not set, falling back to the curated seed layer")
        return None
    return client


def main() -> int:
    settings = ensure_directories()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--specs", type=Path, default=settings.paths.specs_dir)
    parser.add_argument("--out", type=Path, default=settings.paths.ontology_path)
    parser.add_argument("--offline", action="store_true", help="use the curated seed layer only")
    parser.add_argument("--batch-size", type=int, default=40)
    parser.add_argument("--limit-specs", type=int, default=0)
    args = parser.parse_args()

    samples, stats = field_inventory(args.specs, args.limit_specs, settings)
    print(f"inventory: {stats['specs']} specs, {stats['fields']} fields, {stats['errors']} unreadable")
    if not samples:
        print(f"no specs found in {args.specs}; run scripts/fetch_specs.py first")
        return 1

    client = build_client(args.offline)
    log_dir = settings.paths.out_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "ontology_violations.jsonl"
    layer = generate_domain_layer(
        samples,
        client,
        settings=settings,
        batch_size=args.batch_size,
        violation_log_path=log_path,
    )

    ontology = load_upper()
    for triple in units_graph():
        ontology.add(triple)
    for triple in concepts_to_graph(layer.concepts):
        ontology.add(triple)
    result = validate_graph(ontology)
    if not result.conforms:
        print(f"ontology still invalid: {len(result.violations)} violations (see {log_path})")
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    ontology.serialize(destination=args.out, format="turtle")
    save_concepts(layer.concepts, args.out.parent / "domain.ttl")
    summary = {
        "source": layer.source,
        "concepts": len(layer.concepts),
        "uncovered_fields": len(layer.uncovered_fields),
        "violations_found": layer.violations_found,
        "violations_fixed": layer.violations_fixed,
        "repair_rounds": layer.attempts,
        "llm_batches": layer.batches,
        "failed_batches": getattr(layer, "failed_batches", 0),
        "specs": stats,
        "ontology_path": str(args.out),
    }
    summary_path = settings.paths.out_dir / "logs" / "ontology_build.json"
    summary_path.write_text(json.dumps(summary, indent=1), encoding="utf-8")

    print("\n| item | value |")
    print("| --- | --- |")
    for key in ("source", "concepts", "uncovered_fields", "violations_found", "violations_fixed", "repair_rounds", "llm_batches"):
        print(f"| {key} | {summary[key]} |")
    print(f"\nontology written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
