from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.services import AppServices, build_services


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        offline_mode=True,
        runtime_dir=tmp_path / "runtime",
        breaker_failure_threshold=2,
        breaker_cooldown_seconds=1,
        request_timeout_seconds=5.0,
    )


@pytest.fixture
def services(settings: Settings) -> AppServices:
    return build_services(settings)


@pytest.fixture
def api(settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app(settings)) as client:
        yield client
