"""Mapping evaluation: accuracy/F1 vs the labelled set, learning curve, cost.

The labelled set (data/eval/mapping_gold.jsonl) is filled by the team after
LLM pre-labelling. --template writes an unlabelled template from the spec corpus.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import _bootstrap  # noqa: F401
from agent_bazaar.config import PathSettings, Settings, ensure_directories, get_settings
from agent_bazaar.evaluation.dataset import MappingExample, load_dataset, save_dataset, to_field_spec
from agent_bazaar.evaluation.learning_curve import curve_to_markdown, run_learning_curve
from agent_bazaar.evaluation.metrics import (
    compute_accuracy,
    confusion_pairs,
    domain_of_concept,
    format_markdown_table,
    latency_stats,
    surface_accuracy_by_group,
)
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore
from agent_bazaar.llm.client import build_llm_client
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.mapper.memory import CorrectionMemory
from agent_bazaar.messages.schema import CorrectionSubmit, MapRequest
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.protocols import CORRECTIONS
from agent_bazaar.vec import HashingEmbedder, VectorIndex, VectorService

REPO_ROOT = Path(__file__).resolve().parents[1]


def local(reference: str) -> str:
    text = str(reference or "").strip()
    return text.rsplit("#", 1)[-1] if "#" in text else text


def build_offline_stack(settings: Settings, workdir: Path):
    ontology = upper_with_units()
    ontology_path = get_settings().paths.ontology_path
    if ontology_path.exists():
        ontology.parse(ontology_path, format="turtle")
    else:
        for triple in concepts_to_graph(merge_concepts(SEED_CONCEPTS)):
            ontology.add(triple)
    store = KgStore(graph=ontology, settings=settings)
    embedder = HashingEmbedder(settings.embedding.fallback_dim)
    vector = VectorService(embedder, VectorIndex(embedder.dim))
    mapper = MapperAgent(
        store,
        vector,
        client=None,
        ingester=IngestionUtility(settings.ingestion),
        settings=settings,
        use_llm=False,
    )
    mapper.build_index()
    return store, vector, mapper


def emit_template(specs_dir: Path, out_path: Path) -> int:
    examples: list[MappingExample] = []
    files = sorted(p for p in specs_dir.glob("*.json") if p.name != "manifest.json")
    utility = IngestionUtility()
    for path in files:
        try:
            spec = utility.ingest(path)
        except Exception:
            continue
        for field in spec.fields:
            examples.append(
                MappingExample(
                    id=f"{spec.tool_id}:{field.path}",
                    tool_id=spec.tool_id,
                    field_name=field.path.rsplit(".", 1)[-1],
                    field_type=field.type,
                    field_description=field.description,
                    sample_value=field.sample_value,
                    split="unlabelled",
                    source=path.name,
                )
            )
    save_dataset(examples, out_path)
    print(f"template: {len(examples)} unlabelled fields written to {out_path}")
    print("next: pre-label with the LLM, then two members label at least 40 items blind before seeing pre-labels (Cohen's kappa)")
    return 0


def main() -> int:
    settings = ensure_directories()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=REPO_ROOT / "data" / "eval" / "mapping_gold.jsonl")
    parser.add_argument("--specs", type=Path, default=settings.paths.specs_dir / "seed")
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--learning-curve", action="store_true")
    parser.add_argument("--llm", action="store_true", help="use the LLM mapper (needs an API key and cache)")
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT / "data" / "eval_run")
    args = parser.parse_args()

    if args.template:
        return emit_template(args.specs, args.dataset)

    if not args.dataset.exists():
        print(f"dataset not found: {args.dataset}; run with --template to emit one from the corpus")
        return 1
    examples = [e for e in load_dataset(args.dataset) if e.gold_concept]
    if not examples:
        print(f"dataset has no gold labels yet: {args.dataset}")
        return 1

    workdir = args.workdir
    paths = PathSettings(
        data_dir=workdir,
        specs_dir=workdir / "specs",
        cache_dir=workdir / "cache",
        out_dir=workdir / "out",
        memory_dir=workdir / "memory",
        staging_dir=workdir / "staging",
        vectors_dir=workdir / "vectors",
    )
    run_settings = Settings(paths=paths)
    ensure_directories(run_settings)

    client = build_llm_client() if args.llm else None
    if args.llm and client is None:
        print("LLM requested but unavailable; falling back to heuristic mapping")
    store, vector, mapper = build_offline_stack(run_settings, workdir)
    if client is not None:
        mapper.client = client
        mapper.use_llm = True

    predicted: list[str] = []
    gold: list[str] = []
    groups: list[str] = []
    latencies: list[float] = []
    for example in examples:
        started = time.perf_counter()
        result = mapper.map_fields(MapRequest(tool_id=example.tool_id, fields=[to_field_spec(example)]))
        latencies.append((time.perf_counter() - started) * 1000)
        mapping = next((m for m in result.mappings if m.field_path == example.id), None)
        predicted.append(local(mapping.concept) if mapping else "unmapped")
        gold.append(local(example.gold_concept))
        groups.append(domain_of_concept(example.gold_concept))

    report = compute_accuracy(predicted, gold)
    print("\n## Mapping accuracy (concept level)\n")
    print(format_markdown_table(
        ["n", "accuracy", "macro F1", "micro F1", "macro P", "macro R"],
        [[report.n, f"{report.accuracy:.3f}", f"{report.macro_f1:.3f}", f"{report.micro_f1:.3f}", f"{report.macro_precision:.3f}", f"{report.macro_recall:.3f}"]],
    ))
    print("\n### By domain\n")
    by_domain = surface_accuracy_by_group(predicted, gold, groups)
    print(format_markdown_table(
        ["domain", "n", "accuracy", "macro F1"],
        [[d, r.n, f"{r.accuracy:.3f}", f"{r.macro_f1:.3f}"] for d, r in sorted(by_domain.items())],
    ))
    errors = confusion_pairs(predicted, gold)[:10]
    print("\n### Top confusions (predicted -> gold)\n")
    print(format_markdown_table(["predicted", "gold", "count"], [[p, g, c] for p, g, c in errors]))
    print("\n### Cost\n")
    print(format_markdown_table(["metric", "value"], [[k, v] for k, v in latency_stats(latencies).items()]))

    corrections = [e for e in load_dataset(args.dataset) if e.gold_concept and e.split == "dev"]
    if args.learning_curve:
        if not corrections:
            print("\nlearning curve skipped: no dev-split correction examples in the dataset")
        else:
            def reset() -> None:
                memory_file = run_settings.paths.memory_dir / "corrections.jsonl"
                if memory_file.exists():
                    memory_file.unlink()
                mapper.memory = CorrectionMemory(run_settings.paths.memory_dir)
                try:
                    mapper.vector.index.clear(CORRECTIONS)
                except Exception:
                    pass
                mapper.build_index()

            curve = run_learning_curve(mapper, examples, corrections, counts=(0, 5, 10, 20), reset=reset)
            print("\n## Learning curve\n")
            print(curve_to_markdown(curve))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
