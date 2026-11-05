from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_api(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    return TestClient(create_app(settings))


def test_health_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_ready_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/health/ready")
        assert response.status_code == 200


def test_metrics_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/metrics")
        assert response.status_code == 200
        assert "agent_bazaar_http_requests_total" in response.text


def test_admin_stats_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/stats")
        assert response.status_code == 200
        assert "requests" in response.json()


def test_admin_versions_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/versions")
        assert response.status_code == 200
        assert response.json()["counts"]["concepts"] > 0


def test_admin_cache_clear(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.post("/api/admin/cache/clear")
        assert response.status_code == 200
        assert response.json()["status"] == "cleared"


def test_mcp_audit_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/mcp/audit")
        assert response.status_code == 200
        assert "events" in response.json()


def test_mcp_prompts_endpoint(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/mcp/prompts")
        assert response.status_code == 200
        assert response.json()["prompts"]


def test_agents_health_scores(tmp_path) -> None:
    with make_api(tmp_path) as api:
        agents = api.get("/api/agents").json()["agents"]
        assert all("health" in agent for agent in agents)


def test_export_endpoint_keys(tmp_path) -> None:
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/export")
        assert response.status_code == 200
        assert {"tasks", "providers", "tools", "trust"}.issubset(response.json())
