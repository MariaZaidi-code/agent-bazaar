from __future__ import annotations

from app.knowledge.ontology import Ontology


def test_ontology_load():
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    assert ontology is not None
    assert len(ontology.concepts) > 0


def test_ontology_concepts(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    assert len(ontology.concepts) >= 5
    assert len(ontology.capabilities) > 0


def test_ontology_unit_registry(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    assert len(ontology.units) > 0
    assert len(ontology.units) >= 10


def test_ontology_capabilities(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    caps = ontology.capabilities
    assert len(caps) > 0


def test_ontology_concept_count(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    assert len(ontology.concepts) > 50


def test_ontology_is_subtype(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    concepts = list(ontology.concepts.keys())[:5]
    for concept in concepts:
        result = ontology.is_subtype(concept, concept)
        assert result is True


def test_ontology_capabilities_non_empty(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    caps = ontology.capabilities
    assert len(caps) > 0
    cap_keys = list(caps.keys())[:3]
    for cap_key in cap_keys:
        cap_data = caps[cap_key]
        assert "description" in cap_data


def test_ontology_units_count(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    assert len(ontology.units) >= 10


def test_ontology_units_compatible(tmp_path):
    from pathlib import Path
    ontology_path = Path(__file__).resolve().parents[1] / "app" / "data" / "ontology.json"
    ontology = Ontology.load(ontology_path)
    units = list(ontology.units.keys())[:5]
    for u1 in units:
        for u2 in units:
            result = ontology.units_compatible(u1, u2)
            assert isinstance(result, (bool, tuple, list))