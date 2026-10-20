"""Offline demonstration of the Mapper: mapping, corrections, repair, drift.

Deterministic: hashing embeddings, heuristic mapper, curated seed ontology when
the generated ontology artifact is absent.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401
from agent_bazaar.config import PathSettings, Settings, ensure_directories, get_settings
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.kg import KgStore, describe_graph
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.messages.schema import CorrectionSubmit, DriftAlert, FieldSpec, MapRequest
from agent_bazaar.models import ToolRecord
from agent_bazaar.ontology.domain import SEED_CONCEPTS, concepts_to_graph, merge_concepts
from agent_bazaar.ontology.upper import upper_with_units
from agent_bazaar.pipeline import onboard_spec
from agent_bazaar.vec import HashingEmbedder, VectorIndex, VectorService

REPO_ROOT = Path(__file__).resolve().parents[1]


def build_demo(tmp_root: Path, sample_spec: Path):
    paths = PathSettings(
        data_dir=tmp_root,
        specs_dir=tmp_root / "specs",
        cache_dir=tmp_root / "cache",
        out_dir=tmp_root / "out",
        memory_dir=tmp_root / "memory",
        staging_dir=tmp_root / "staging",
        vectors_dir=tmp_root / "vectors",
    )
    settings = Settings(paths=paths)
    ensure_directories(settings)

    ontology = upper_with_units()
    concepts = merge_concepts(SEED_CONCEPTS)
    ontology_path = get_settings().paths.ontology_path
    if ontology_path.exists():
        ontology.parse(ontology_path, format="turtle")
    else:
        for triple in concepts_to_graph(concepts):
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
    spec = mapper.ingester.ingest(sample_spec)
    return settings, store, vector, mapper, spec


def print_mappings(title: str, result) -> None:
    print(f"\n{title}")
    print("| field | concept | unit | confidence | status | reason |")
    print("| --- | --- | --- | --- | --- | --- |")
    for mapping in result.mappings:
        print(
            f"| {mapping.field_path.split('.', 1)[-1]} | {mapping.concept_label or mapping.concept} "
            f"| {mapping.unit or '-'} | {mapping.confidence} "
            f"| {getattr(mapping.status, 'value', mapping.status)} | {mapping.reason[:60]} |"
        )
    for field in result.unmapped:
        print(f"| {field.field_path.split('.', 1)[-1]} | unmapped | - | - | unmapped | queued for human review |")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=Path, default=REPO_ROOT / "tests" / "fixtures" / "sample_openapi.json")
    parser.add_argument("--workdir", type=Path, default=REPO_ROOT / "data" / "demo")
    args = parser.parse_args()

    settings, store, vector, mapper, spec = build_demo(args.workdir, args.sample)
    print(f"demo workspace: {args.workdir}")

    outcome = onboard_spec(spec, mapper, store, vector=vector, write=True, tool_id="demo-weather")
    tool_record: ToolRecord = outcome.record
    result = outcome.result
    print_mappings("1. Field mapping (offline heuristic)", result)

    temperature = next((m for m in result.mappings if "temperature" in m.field_path), None)
    if temperature is not None:
        correction = CorrectionSubmit(
            tool_id=tool_record.tool_id,
            field_path=temperature.field_path,
            corrected_concept="ab:FeelsLikeTemperature",
            corrected_unit="Celsius",
            note="feels-like, not dry-bulb",
            submitted_by="demo",
            sender="developer",
        )
        decision = mapper.submit_correction(correction)
        print(f"\n2. Correction staging: good correction -> {decision['status']} ({decision['reason'] or 'validated and promoted'})")
        print(f"   staging stats: {decision['stats']}")
        bad = CorrectionSubmit(
            tool_id=tool_record.tool_id,
            field_path=temperature.field_path,
            corrected_concept="ab:Unicorn",
            submitted_by="demo",
            sender="developer",
        )
        bad_decision = mapper.submit_correction(bad)
        print(f"   injected bad correction -> {bad_decision['status']} ({bad_decision['reason']})")

        alert = DriftAlert(
            tool_id=tool_record.tool_id,
            field_path=temperature.field_path,
            old_description="temperature in Celsius",
            new_sample={"value": 86.0, "unit_hint": "feels_like_fahrenheit"},
            evidence={"probe": "mock drift injection"},
            sender="auditor",
        )
        drift_result = mapper.handle_drift_alert(alert)
        print_mappings("3. Drift re-mapping (DriftAlert from the Auditor)", drift_result)

    field_summary = store.concept_for_field(tool_record.tool_id, temperature.field_path) if temperature else None
    print(f"\n4. Knowledge graph facts for {tool_record.tool_id}: {describe_graph(store.graph)}")
    print(f"   concept_for_field(temperature) -> {field_summary}")
    print(f"   vector collections: ontology_terms={vector.count('ontology_terms')}, corrections={vector.count('corrections')}")
    print("\ndone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
