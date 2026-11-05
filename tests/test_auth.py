from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_auth_flow_and_user_data(tmp_path) -> None:
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    with TestClient(create_app(settings)) as api:
        signup = api.post("/api/auth/signup", json={"email": "user@example.com", "password": "password123"})
        assert signup.status_code == 200
        user = signup.json()["user"]

        login = api.post("/api/auth/login", json={"email": "user@example.com", "password": "password123"})
        assert login.status_code == 200
        assert api.get("/api/auth/me").json()["user"]["id"] == user["id"]

        assert api.put("/api/auth/settings", json={"theme": "light"}).status_code == 200
        assert api.get("/api/auth/settings").json()["settings"]["theme"] == "light"

        assert api.post("/api/favorites", json={"tool_id": "open-meteo-forecast", "note": "fav"}).status_code == 200
        assert api.get("/api/favorites").json()["favorites"]

        task = api.post("/api/tasks", json={"task": "What is the weather in Paris?"})
        assert task.status_code == 200
        task_id = task.json()["task_id"]
        assert api.post(f"/api/tasks/{task_id}/save", json={"note": "saved"}).status_code == 200
        assert api.get("/api/tasks/saved").json()["saved_tasks"]

        assert api.post("/api/workflows", json={"name": "wf", "steps": [{"tool": "open-meteo-forecast"}]}).status_code == 200
        assert api.get("/api/workflows").json()["workflows"]

        assert api.post("/api/auth/api-keys", json={"name": "openai", "value": "secret"}).status_code == 200
        assert api.get("/api/auth/api-keys").json()["api_keys"]
        assert api.get("/api/audit-log").status_code == 200

        assert api.post("/api/auth/logout").status_code == 200
        assert api.get("/api/auth/me").json()["user"] is None
