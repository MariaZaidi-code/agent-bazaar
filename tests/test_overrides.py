from __future__ import annotations

from pathlib import Path

import yaml
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_override_review(tmp_path) -> None:
    override_path = Path("data/overrides/pricing.yaml")
    backup = override_path.read_text(encoding="utf-8")
    try:
        override_path.write_text(
            "tools:\n  open-meteo-forecast:\n    pricing_tier: free\n    reviewer: \"\"\n",
            encoding="utf-8",
        )
        settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
        with TestClient(create_app(settings)) as api:
            listed = api.get("/api/admin/overrides").json()["overrides"]
            assert "open-meteo-forecast" in listed
            reviewed = api.post("/api/admin/overrides/open-meteo-forecast/review", json={"reviewer": "Rameen"}).json()
            assert reviewed["override"]["reviewer"] == "Rameen"
            saved = yaml.safe_load(override_path.read_text(encoding="utf-8"))
            assert saved["tools"]["open-meteo-forecast"]["reviewer"] == "Rameen"
    finally:
        override_path.write_text(backup, encoding="utf-8")
