from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def make_api(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=True, rate_limit_requests=100)
    return TestClient(create_app(settings))


def test_metrics_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        api.get("/api/health")
        api.get("/api/tools")
        response = api.get("/api/metrics")
        assert response.status_code == 200
        text = response.text
        assert "agent_bazaar_http_requests_total" in text
        assert "agent_bazaar_http_errors_total" in text


def test_correlation_id_header(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/health", headers={"X-Correlation-ID": "test-corr-123"})
        assert response.status_code == 200
        assert response.headers.get("X-Correlation-ID") == "test-corr-123"


def test_rate_limit_headers(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/health")
        assert response.status_code == 200
        assert "X-Correlation-ID" in response.headers
        assert "X-Response-Time-Ms" in response.headers


def test_admin_webhooks_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/webhooks")
        assert response.status_code == 200
        data = response.json()
        assert "webhooks" in data


def test_admin_webhook_create_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.post(
            "/api/admin/webhooks",
            json={"url": "https://example.test/hooks/agent-bazaar", "events": ["task.completed"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "webhook" in data


def test_admin_webhook_delete_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        created = api.post(
            "/api/admin/webhooks",
            json={"url": "https://example.test/hooks/agent-bazaar", "events": ["task.completed"]},
        )
        webhook_id = created.json()["webhook"]["id"]
        delete_response = api.delete(f"/api/admin/webhooks/{webhook_id}")
        assert delete_response.status_code == 200
        delete_response = api.delete(f"/api/admin/webhooks/{webhook_id}")
        assert delete_response.status_code == 404


def test_admin_jobs_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/jobs")
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data


def test_admin_jobs_submit_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.post("/api/admin/jobs", json={"kind": "export_graph"})
        assert response.status_code == 200
        data = response.json()
        assert "job" in data
        assert "id" in data["job"]


def test_admin_jobs_invalid_kind(tmp_path):
    with make_api(tmp_path) as api:
        response = api.post("/api/admin/jobs", json={"kind": "invalid_kind"})
        assert response.status_code == 422


def test_tasks_recent_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/tasks/recent")
        assert response.status_code == 200


def test_health_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "version" in data


def test_health_ready_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/health/ready")
        assert response.status_code == 200


def test_admin_stats_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/stats")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "uptime_seconds" in data
        assert "mode" in data
        assert "requests" in data
        assert "jobs" in data
        assert "webhooks" in data
        assert "knowledge_available" in data
        assert "rate_limit" in data


def test_admin_versions_endpoint(tmp_path):
    with make_api(tmp_path) as api:
        response = api.get("/api/admin/versions")
        assert response.status_code == 200
        data = response.json()
        assert "app_version" in data
        assert "counts" in data
        assert "concepts" in data["counts"]
        assert "tools" in data["counts"]
        assert "datasets" in data
        assert "artifacts" in data