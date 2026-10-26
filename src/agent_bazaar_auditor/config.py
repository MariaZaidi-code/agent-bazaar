from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .paths import CACHE_DIR, DATA_DIR, OUTPUTS_DIR


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path = DATA_DIR
    outputs_dir: Path = OUTPUTS_DIR
    cache_dir: Path = CACHE_DIR
    live: bool = False
    embedding_dimensions: int = 256
    drift_threshold: float = 0.15
    drift_mode: str = "full"
    trust_demotion_threshold: float = 0.4
    trust_registry_url: str = ""
    request_timeout_seconds: float = 15.0
    scheduler_base_interval_seconds: float = 3600.0
    scheduler_unstable_interval_seconds: float = 300.0
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""

    @classmethod
    def from_env(cls) -> Settings:
        mode = os.environ.get("ABA_DRIFT_MODE", "full").strip().lower()
        if mode not in {"full", "rule_only", "embedding_only"}:
            mode = "full"
        return cls(
            data_dir=Path(os.environ.get("ABA_DATA_DIR", DATA_DIR)),
            outputs_dir=Path(os.environ.get("ABA_OUTPUT_DIR", OUTPUTS_DIR)),
            cache_dir=Path(os.environ.get("ABA_CACHE_DIR", CACHE_DIR)),
            live=_env_bool("ABA_LIVE", False),
            embedding_dimensions=_env_int("ABA_EMBEDDING_DIMENSIONS", 256),
            drift_threshold=_env_float("ABA_DRIFT_THRESHOLD", 0.15),
            drift_mode=mode,
            trust_demotion_threshold=_env_float("ABA_TRUST_DEMOTION_THRESHOLD", 0.4),
            trust_registry_url=os.environ.get("ABA_TRUST_REGISTRY_URL", ""),
            request_timeout_seconds=_env_float("ABA_REQUEST_TIMEOUT", 15.0),
            scheduler_base_interval_seconds=_env_float("ABA_SCHEDULER_BASE_INTERVAL", 3600.0),
            scheduler_unstable_interval_seconds=_env_float("ABA_SCHEDULER_UNSTABLE_INTERVAL", 300.0),
            llm_base_url=os.environ.get("ABA_LLM_BASE_URL", ""),
            llm_api_key=os.environ.get("ABA_LLM_API_KEY", ""),
            llm_model=os.environ.get("ABA_LLM_MODEL", ""),
        )

    def __post_init__(self) -> None:
        self.data_dir = Path(self.data_dir)
        self.outputs_dir = Path(self.outputs_dir)
        self.cache_dir = Path(self.cache_dir)

    def prepare(self) -> Settings:
        for directory in (self.outputs_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)
        return self
