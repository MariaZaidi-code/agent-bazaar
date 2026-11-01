from __future__ import annotations

from fastapi.testclient import TestClient


def test_readiness_reports_loaded_providers(api: TestClient) -> None:
    response = api.get("/readyz")

    assert response.status_code == 200
    payload = response.json()
    assert payload["ready"] is True
    assert payload["providers"] >= 60


def test_metrics_expose_prometheus_text(api: TestClient) -> None:
    api.get("/api/health")
    response = api.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "agent_bazaar_requests_total" in body
    assert "agent_bazaar_tools_total" in body
    assert 'agent_bazaar_trust_score{provider="open-meteo"}' in body


def test_security_headers_are_set(api: TestClient) -> None:
    response = api.get("/")

    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    csp = response.headers["content-security-policy"]
    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "worker-src 'self'" in csp


def test_manifest_and_service_worker_are_served(api: TestClient) -> None:
    manifest = api.get("/manifest.webmanifest")
    assert manifest.status_code == 200
    assert manifest.json()["name"] == "Agent Bazaar"

    worker = api.get("/sw.js")
    assert worker.status_code == 200
    assert worker.headers["service-worker-allowed"] == "/"
    assert "agent-bazaar-v1" in worker.text
