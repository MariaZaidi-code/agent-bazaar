from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from app import __version__
from app.config import BASE_DIR, Settings


def fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "exists": False, "sha256": "", "bytes": 0}
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return {
        "path": str(path),
        "exists": True,
        "sha256": digest.hexdigest(),
        "bytes": path.stat().st_size,
    }


def _json_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    return {
        key: payload[key]
        for key in ("schema_version", "version", "name", "counts")
        if key in payload
    }


def build_version_manifest(settings: Settings, ontology_concepts: int, graph_tools: int) -> dict[str, Any]:
    data_files = {
        "ontology": settings.ontology_file,
        "tools": settings.tools_file,
        "seeded_claims": BASE_DIR / "data" / "seeded_claims.json",
        "drift_scenarios": BASE_DIR / "data" / "drift_scenarios.json",
        "graph": settings.knowledge_graph_file,
        "rdf_ontology": settings.knowledge_ontology_file,
    }
    return {
        "app_version": __version__,
        "knowledge_backend": settings.knowledge_backend,
        "counts": {"concepts": ontology_concepts, "tools": graph_tools},
        "datasets": {
            "seeded_claims": _json_metadata(data_files["seeded_claims"]),
            "drift_scenarios": _json_metadata(data_files["drift_scenarios"]),
        },
        "artifacts": {name: fingerprint(path) for name, path in data_files.items()},
    }
