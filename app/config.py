from __future__ import annotations

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AB_",
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Agent Bazaar"
    data_dir: Path = BASE_DIR / "app" / "data"
    runtime_dir: Path = BASE_DIR / "data" / "runtime"
    offline_mode: bool = False
    request_timeout_seconds: float = 15.0
    cache_ttl_seconds: int = 86_400
    seed_document: bool = True

    llm_provider: str = "none"
    llm_api_key: str | None = None
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_model: str = "meta-llama/llama-3.3-70b-instruct:free"
    llm_timeout_seconds: float = 45.0

    ranking_top_k: int = 8
    graph_expansion: int = 3
    relevance_weight: float = 1.0
    trust_weight: float = 1.0
    contradicted_penalty: float = 0.6
    exclude_contradicted: bool = False

    trust_signal_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "probe": 1.0,
            "call": 1.0,
            "schema": 0.5,
            "rating": 0.75,
            "contradiction": 2.0,
        }
    )
    trust_demotion_threshold: float = 0.40
    trust_min_evidence: int = 3

    breaker_failure_threshold: int = 2
    breaker_cooldown_seconds: int = 30

    use_ontology: bool = True
    use_auditor: bool = True
    use_trust: bool = True
    use_feedback: bool = True
    use_substitution: bool = True
    use_circuit_breaker: bool = True

    @field_validator("data_dir", "runtime_dir", mode="after")
    @classmethod
    def resolve_path(cls, value: Path) -> Path:
        return value if value.is_absolute() else (BASE_DIR / value).resolve()

    @property
    def uploads_dir(self) -> Path:
        return self.runtime_dir / "uploads"

    @property
    def cache_db(self) -> Path:
        return self.runtime_dir / "cache.db"

    @property
    def traces_db(self) -> Path:
        return self.runtime_dir / "traces.db"

    @property
    def trust_db(self) -> Path:
        return self.runtime_dir / "trust.db"

    @property
    def documents_db(self) -> Path:
        return self.runtime_dir / "documents.db"

    @property
    def sample_sql_db(self) -> Path:
        return self.runtime_dir / "sample_university.db"

    @property
    def fixtures_dir(self) -> Path:
        return self.data_dir / "fixtures"

    @property
    def tools_file(self) -> Path:
        return self.data_dir / "tools.json"

    @property
    def ontology_file(self) -> Path:
        return self.data_dir / "ontology.json"

    def ensure_dirs(self) -> None:
        for path in (self.runtime_dir, self.uploads_dir):
            path.mkdir(parents=True, exist_ok=True)

    def ablate(self, **changes: bool) -> Settings:
        return self.model_copy(update=changes)
