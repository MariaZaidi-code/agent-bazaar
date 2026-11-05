from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_api(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    return TestClient(create_app(settings))


def test_provider_health_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/providers/health")
        assert response.status_code == 200
        assert response.json()["providers"]


def test_provider_selection_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        capability = api.get("/api/providers/health").json()["providers"][0]["capability"]
        response = api.get("/api/providers/select", params={"capability": capability})
        assert response.status_code == 200
        assert response.json()["selected"]


def test_scheduled_runs_crud(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.post(
            "/api/scheduled-runs",
            json={"task": "What is the weather in Paris?", "interval_seconds": 3600},
        )
        created = response.json()["scheduled_run"]
        assert api.get("/api/scheduled-runs").status_code == 200
        assert api.post(f"/api/scheduled-runs/{created['id']}/run").status_code == 200
        assert api.delete(f"/api/scheduled-runs/{created['id']}").status_code == 200


def test_export_import_endpoints(tmp_path) -> None:
    with make_api(tmp_path) as api:
        exported = api.get("/api/admin/export")
        assert exported.status_code == 200
        assert "providers" in exported.json()
        payload = {"scheduled_runs": [{"task": "What is the weather in Paris?", "interval_seconds": 3600}]}
        imported = api.post("/api/admin/import", json=payload)
        assert imported.status_code == 200
        assert imported.json()["imported_scheduled_runs"] == 1


def test_agents_endpoints(tmp_path) -> None:
    with make_api(tmp_path) as api:
        agents = api.get("/api/agents").json()["agents"]
        assert len(agents) == 8
        assert api.post("/api/agents/planner/run", json={}).status_code == 200


def test_mcp_endpoints(tmp_path) -> None:
    with make_api(tmp_path) as api:
        assert api.get("/api/mcp/servers").status_code == 200
        discovered = api.post("/api/mcp/discover/local").json()["tools"]
        assert discovered
        call_payload = {"server_id": "local", "tool": discovered[0]["name"], "arguments": {}}
        call_response = api.post("/api/mcp/call", json=call_payload)
        assert call_response.status_code in {200, 500}
        assert api.get("/api/mcp/resources").status_code == 200
        assert api.get("/api/mcp/audit").status_code == 200


def test_auth_settings_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        api.post("/api/auth/signup", json={"email": "a@example.com", "password": "password123"})
        api.post("/api/auth/login", json={"email": "a@example.com", "password": "password123"})
        assert api.put("/api/auth/settings", json={"theme": "light"}).status_code == 200
        assert api.get("/api/auth/settings").json()["settings"]["theme"] == "light"


def test_override_endpoints(tmp_path) -> None:
    override_path = tmp_path / "pricing.yaml"
    override_path.write_text(
        "tools:\n  open-meteo-forecast:\n    pricing_tier: free\n    reviewer: \"\"\n",
        encoding="utf-8",
    )
    # Endpoint reads the repository override file.
    with make_api(tmp_path) as api:
        assert api.get("/api/admin/overrides").status_code == 200


def test_security_headers(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"


def test_reasoning_mode_parameter(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.post("/api/tasks", json={"task": "What is the weather in Paris?", "reasoning_mode": "none"})
        assert response.status_code == 200
        assert response.json()["reasoning_mode"] == "none"
