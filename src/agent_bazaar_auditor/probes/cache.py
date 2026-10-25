from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


class ProbeCache:
    def __init__(self, root: Path | str = ".cache/probes") -> None:
        self.root = Path(root)

    def path_for(self, tool_id: str) -> Path:
        safe = "".join(character if character.isalnum() or character in {"-", "_", "."} else "_" for character in tool_id)
        return self.root / f"{safe}.json"

    def get(self, tool_id: str, ttl_seconds: int, now: float | None = None) -> dict[str, Any] | None:
        path = self.path_for(tool_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        current = time.time() if now is None else now
        if current - float(data.get("cached_at", 0)) > ttl_seconds:
            return None
        return data

    def set(self, tool_id: str, payload: Any, status_code: int, url: str = "", raw_text: str = "", now: float | None = None) -> dict[str, Any]:
        path = self.path_for(tool_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "tool_id": tool_id,
            "payload": payload,
            "status_code": status_code,
            "url": url,
            "raw_text": raw_text,
            "cached_at": time.time() if now is None else now,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return data
