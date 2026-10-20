"""Disk cache for LLM calls (NFR2: every call and response is cached)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


class JsonDiskCache:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self._hits = 0
        self._misses = 0

    @staticmethod
    def make_key(*parts: str) -> str:
        digest = hashlib.sha256("\u241f".join(parts).encode("utf-8")).hexdigest()
        return digest[:32]

    def _path_for(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def get(self, key: str) -> dict[str, Any] | None:
        path = self._path_for(key)
        if not path.exists():
            self._misses += 1
            return None
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self._misses += 1
            return None
        self._hits += 1
        return value

    def set(self, key: str, value: dict[str, Any]) -> None:
        path = self._path_for(key)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        tmp.replace(path)

    def stats(self) -> dict[str, int]:
        return {"hits": self._hits, "misses": self._misses, "entries": len(list(self.directory.glob("*.json")))}
