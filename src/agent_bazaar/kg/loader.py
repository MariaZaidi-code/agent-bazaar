"""Normalized spec loading and writing helpers for the knowledge layer."""

from __future__ import annotations

import json
import re
from pathlib import Path

from agent_bazaar.ingestion.models import NormalizedSpec
from agent_bazaar.logging_utils import get_logger

_LOGGER = get_logger("agent_bazaar.kg.loader")
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _safe_filename(tool_id: str) -> str:
    cleaned = _INVALID_FILENAME.sub("-", tool_id).strip(" .")
    return f"{cleaned or 'spec'}.json"


def load_normalized_specs(specs_dir: str | Path) -> list[NormalizedSpec]:
    directory = Path(specs_dir)
    if not directory.exists():
        return []
    specs: list[NormalizedSpec] = []
    for path in sorted(directory.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and isinstance(payload.get("spec"), dict):
                payload = payload["spec"]
            specs.append(NormalizedSpec.model_validate(payload))
        except Exception as error:
            _LOGGER.warning("skipping malformed spec %s: %s", path.name, error)
            continue
    return sorted(specs, key=lambda spec: (spec.tool_id, spec.source, spec.spec_format))


def write_normalized_spec(spec: NormalizedSpec, path: str | Path) -> Path:
    target = Path(path)
    if target.is_dir() or target.suffix.lower() != ".json":
        target = target / _safe_filename(spec.tool_id)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    return target


def load_specs_summary(specs_dir: str | Path) -> list[dict]:
    return [
        {
            "tool_id": spec.tool_id,
            "title": spec.title,
            "endpoint_count": len(spec.endpoints),
            "field_count": len(spec.fields),
            "source": spec.source,
        }
        for spec in load_normalized_specs(specs_dir)
    ]
