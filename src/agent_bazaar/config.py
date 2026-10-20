"""Configuration loading for the knowledge layer.

Defaults are code-defined; an optional config/settings.yaml overrides them and
environment variables only ever carry secrets (API keys).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "groq"
    temperature: float = 0.0
    timeout_s: int = 90
    max_retries: int = 3
    models: dict[str, str] = field(
        default_factory=lambda: {
            "groq": "llama-3.3-70b-versatile",
            "gemini": "gemini-2.0-flash",
            "openrouter": "meta-llama/llama-3.3-70b-instruct:free",
        }
    )

    def model_for(self, provider: str | None = None) -> str:
        return self.models.get(provider or self.provider, "llama-3.3-70b-versatile")


@dataclass(frozen=True)
class EmbeddingSettings:
    model: str = "BAAI/bge-small-en-v1.5"
    fallback_dim: int = 384
    use_fallback: str = "auto"


@dataclass(frozen=True)
class MapperSettings:
    max_repair_attempts: int = 3
    top_k_terms: int = 12
    top_k_corrections: int = 8
    min_confidence: float = 0.0
    promotion_requires_rules_pass: bool = True


@dataclass(frozen=True)
class IngestionSettings:
    chunk_size_chars: int = 800
    chunk_overlap_chars: int = 120


@dataclass(frozen=True)
class PathSettings:
    data_dir: Path = REPO_ROOT / "data"
    specs_dir: Path = REPO_ROOT / "data" / "specs"
    cache_dir: Path = REPO_ROOT / "data" / "cache"
    out_dir: Path = REPO_ROOT / "data" / "out"
    memory_dir: Path = REPO_ROOT / "data" / "memory"
    staging_dir: Path = REPO_ROOT / "data" / "staging"
    vectors_dir: Path = REPO_ROOT / "data" / "vectors"

    @property
    def ontology_path(self) -> Path:
        return self.out_dir / "ontology.ttl"

    @property
    def graph_path(self) -> Path:
        return self.out_dir / "graph.ttl"

    @property
    def shapes_path(self) -> Path:
        return REPO_ROOT / "src" / "agent_bazaar" / "ontology" / "shapes.ttl"


@dataclass(frozen=True)
class Settings:
    llm: LLMSettings = field(default_factory=LLMSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)
    mapper: MapperSettings = field(default_factory=MapperSettings)
    ingestion: IngestionSettings = field(default_factory=IngestionSettings)
    paths: PathSettings = field(default_factory=PathSettings)


def _resolve_paths(raw: dict, root: Path) -> PathSettings:
    base = PathSettings()
    paths = raw or {}
    kwargs = {}
    for key in ("data_dir", "specs_dir", "cache_dir", "out_dir", "memory_dir", "staging_dir", "vectors_dir"):
        if key in paths:
            value = Path(paths[key])
            kwargs[key] = value if value.is_absolute() else root / value
    merged = base
    if kwargs:
        merged = PathSettings(
            data_dir=kwargs.get("data_dir", base.data_dir),
            specs_dir=kwargs.get("specs_dir", kwargs.get("data_dir", base.data_dir) / "specs"),
            cache_dir=kwargs.get("cache_dir", kwargs.get("data_dir", base.data_dir) / "cache"),
            out_dir=kwargs.get("out_dir", kwargs.get("data_dir", base.data_dir) / "out"),
            memory_dir=kwargs.get("memory_dir", kwargs.get("data_dir", base.data_dir) / "memory"),
            staging_dir=kwargs.get("staging_dir", kwargs.get("data_dir", base.data_dir) / "staging"),
            vectors_dir=kwargs.get("vectors_dir", kwargs.get("data_dir", base.data_dir) / "vectors"),
        )
    return merged


def load_settings(path: Path | None = None) -> Settings:
    path = path or DEFAULT_SETTINGS_PATH
    raw: dict = {}
    if path.exists():
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    llm = LLMSettings(**{k: v for k, v in (raw.get("llm") or {}).items() if k in LLMSettings.__dataclass_fields__})
    embedding = EmbeddingSettings(
        **{k: v for k, v in (raw.get("embedding") or {}).items() if k in EmbeddingSettings.__dataclass_fields__}
    )
    mapper = MapperSettings(
        **{k: v for k, v in (raw.get("mapper") or {}).items() if k in MapperSettings.__dataclass_fields__}
    )
    ingestion = IngestionSettings(
        **{k: v for k, v in (raw.get("ingestion") or {}).items() if k in IngestionSettings.__dataclass_fields__}
    )
    paths = _resolve_paths(raw.get("paths") or {}, REPO_ROOT)
    return Settings(llm=llm, embedding=embedding, mapper=mapper, ingestion=ingestion, paths=paths)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


def ensure_directories(settings: Settings | None = None) -> Settings:
    settings = settings or get_settings()
    for directory in (
        settings.paths.data_dir,
        settings.paths.specs_dir,
        settings.paths.cache_dir,
        settings.paths.out_dir,
        settings.paths.memory_dir,
        settings.paths.staging_dir,
        settings.paths.vectors_dir,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    return settings
