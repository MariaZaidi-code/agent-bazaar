from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_admin_stats_webhooks_and_jobs(tmp_path) -> None:
    settings = Settings(
        offline_mode=True,
        runtime_dir=tmp_path / "runtime",
        rate_limit_enabled=True,
        rate_limit_requests=100,
    )
    with TestClient(create_app(settings)) as api:
        response = api.get("/api/admin/stats", headers={"X-Correlation-ID": "corr-admin-1"})
        assert response.status_code == 200
        assert response.headers["X-Correlation-ID"] == "corr-admin-1"
        stats = response.json()
        assert stats["version"]
        assert stats["jobs"] == []
        assert stats["rate_limit"]["enabled"] is True

        versions = api.get("/api/admin/versions").json()
        assert versions["app_version"]
        assert versions["counts"]["concepts"] > 0
        assert versions["datasets"]["seeded_claims"]["counts"]["Verified"] == 62
        assert versions["artifacts"]["seeded_claims"]["sha256"]

        created = api.post(
            "/api/admin/webhooks",
            json={
                "url": "https://example.test/hooks/agent-bazaar",
                "events": ["task.completed"],
                "secret": "not-logged",
            },
        )
        assert created.status_code == 200
        webhook = created.json()["webhook"]
        assert webhook["events"] == ["task.completed"]
        assert "not-logged" not in str(api.get("/api/admin/stats").json())
        assert api.get("/api/admin/webhooks").json()["webhooks"]
        assert api.delete(f"/api/admin/webhooks/{webhook['id']}").status_code == 200
        assert api.delete(f"/api/admin/webhooks/{webhook['id']}").status_code == 404

        submitted = api.post("/api/admin/jobs", json={"kind": "export_graph"})
        assert submitted.status_code == 200
        job_id = submitted.json()["job"]["id"]
        for _ in range(50):
            job = api.get(f"/api/admin/jobs/{job_id}").json()["job"]
            if job["status"] in {"completed", "failed"}:
                break
            time.sleep(0.02)
        assert job["status"] == "completed"
        assert job["result"] is True
        assert api.get("/api/admin/jobs").json()["jobs"]
        assert api.get("/api/admin/jobs/job_missing").status_code == 404


def test_correlation_headers_metrics_and_rate_limit(tmp_path) -> None:
    settings = Settings(
        offline_mode=True,
        runtime_dir=tmp_path / "runtime",
        rate_limit_enabled=True,
        rate_limit_requests=2,
        rate_limit_window_seconds=60,
    )
    with TestClient(create_app(settings)) as api:
        first = api.get("/api/tools")
        assert first.status_code == 200
        assert first.headers["X-Correlation-ID"]
        assert "X-Response-Time-Ms" in first.headers
        assert api.get("/api/tools").status_code == 200
        limited = api.get("/api/tools")
        assert limited.status_code == 429
        assert int(limited.headers["Retry-After"]) >= 1

        metrics = api.get("/api/metrics")
        assert metrics.status_code == 200
        assert "agent_bazaar_http_requests_total" in metrics.text
        assert "agent_bazaar_http_errors_total" in metrics.text

        stats = api.get("/api/admin/stats").json()
        assert stats["requests"]["requests"] >= 3
        assert stats["requests"]["statuses"]["200"] >= 2


def test_webhook_dispatch_records_delivery(services, monkeypatch) -> None:
    import urllib.request

    calls: list[urllib.request.Request] = []

    class FakeResponse:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> None:
            return None

    def fake_urlopen(request, timeout):
        calls.append(request)
        return FakeResponse()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    hook = services.webhooks.register(
        "https://example.test/hooks/agent-bazaar",
        events=["task.completed"],
        secret="test-secret",
    )
    results = services.webhooks.dispatch("task.completed", {"task_id": "task_1"})
    assert results == [{"subscription_id": hook["id"], "status": 202}]
    assert calls[0].headers["X-agent-bazaar-secret"] == "test-secret"
    assert services.webhooks.list()[0]["deliveries"] == 1
