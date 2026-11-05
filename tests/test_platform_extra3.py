from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_api(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    return TestClient(create_app(settings))


def test_health_status(tmp_path) -> None:
    with make_api(tmp_path) as api:
        assert api.get("/api/health").json()["status"] == "ok"


def test_ready_status(tmp_path) -> None:
    with make_api(tmp_path) as api:
        assert api.get("/api/health/ready").status_code == 200


def test_metrics_contains_counters(tmp_path) -> None:
    with make_api(tmp_path) as api:
        text = api.get("/api/metrics").text
        assert "agent_bazaar_http_requests_total" in text


def test_admin_stats_shape(tmp_path) -> None:
    with make_api(tmp_path) as api:
        payload = api.get("/api/admin/stats").json()
        assert "requests" in payload and "jobs" in payload


def test_admin_versions_shape(tmp_path) -> None:
    with make_api(tmp_path) as api:
        payload = api.get("/api/admin/versions").json()
        assert payload["counts"]["concepts"] > 0


def test_admin_cache_clear_status(tmp_path) -> None:
    with make_api(tmp_path) as api:
        assert api.post("/api/admin/cache/clear").json()["status"] == "cleared"


def test_mcp_audit_shape(tmp_path) -> None:
    with make_api(tmp_path) as api:
        payload = api.get("/api/mcp/audit").json()
        assert "events" in payload


def test_mcp_prompts_shape(tmp_path) -> None:
    with make_api(tmp_path) as api:
        payload = api.get("/api/mcp/prompts").json()
        assert "prompts" in payload


def test_agents_health_shape(tmp_path) -> None:
    with make_api(tmp_path) as api:
        agents = api.get("/api/agents").json()["agents"]
        assert all("health" in agent for agent in agents)


def test_admin_export_shape(tmp_path) -> None:
    with make_api(tmp_path) as api:
        payload = api.get("/api/admin/export").json()
        assert {"tasks", "providers", "tools", "trust"}.issubset(payload)
