from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_scheduled_runs(tmp_path) -> None:
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    with TestClient(create_app(settings)) as api:
        created = api.post("/api/scheduled-runs", json={"task": "What is the weather in Paris?", "interval_seconds": 3600}).json()["scheduled_run"]
        assert api.get("/api/scheduled-runs").json()["scheduled_runs"]
        assert api.post(f"/api/scheduled-runs/{created['id']}/run").status_code == 200
        assert api.delete(f"/api/scheduled-runs/{created['id']}").status_code == 200
