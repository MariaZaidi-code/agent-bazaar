from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import BASE_DIR, Settings
from app.services import AppServices, build_services

EVALUATION_DIR = Path(__file__).resolve().parent
DATA_DIR = EVALUATION_DIR / "data"
REPORTS_DIR = BASE_DIR / "reports"


def load_dataset(name: str) -> list[dict[str, Any]]:
    path = DATA_DIR / name
    return json.loads(path.read_text(encoding="utf-8"))


def evaluation_settings(**overrides: Any) -> Settings:
    runtime_dir = Path(tempfile.mkdtemp(prefix="agent-bazaar-evaluation-"))
    values: dict[str, Any] = {
        "offline_mode": True,
        "runtime_dir": runtime_dir,
        "request_timeout_seconds": 5.0,
        "cache_ttl_seconds": 3600,
        "breaker_failure_threshold": 2,
        "breaker_cooldown_seconds": 30,
    }
    values.update(overrides)
    return Settings(**values)


def fresh_services(**overrides: Any) -> AppServices:
    return build_services(evaluation_settings(**overrides))


def utc_timestamp() -> str:
    return datetime.now(UTC).isoformat()


def write_report(name: str, payload: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORTS_DIR / f"{name}.json"
    path.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def summarize_suite(suite: str, metrics: dict[str, Any], rows: int) -> str:
    parts = [f"{suite}: {rows} case(s)"]
    for key in (
        "success_rate",
        "recovery_accuracy",
        "hit_at_k",
        "mrr",
        "selected_tool_accuracy",
        "pass_rate",
    ):
        if key in metrics:
            parts.append(f"{key}={metrics[key]}")
    return " | ".join(parts)
