from __future__ import annotations

from fastapi.testclient import TestClient

from app.agents.auditor_bridge import TOOL_ALIASES
from app.schemas import Candidate, ClaimLabel
from app.services import AppServices


def _candidate(services: AppServices, tool_id: str) -> Candidate:
    tool = services.graph.get(tool_id)
    assert tool is not None
    return Candidate(tool=tool)


async def test_catalog_candidates_use_the_real_auditor(services: AppServices) -> None:
    candidates = [
        _candidate(services, "open-meteo-forecast"),
        _candidate(services, "frankfurter-currency"),
    ]
    result = await services.auditor.verify("task", "subgoal", candidates, "corr")

    assert result.overall["open-meteo-forecast"] is ClaimLabel.verified
    assert result.overall["frankfurter-currency"] is ClaimLabel.supported
    assert result.labels["open-meteo-forecast"]
    assert any(
        item.label is ClaimLabel.verified
        for item in result.labels["open-meteo-forecast"]
    )
    assert all(item.tool_id == "open-meteo-forecast" for item in result.labels["open-meteo-forecast"])


async def test_local_candidates_keep_the_seeded_fallback(services: AppServices) -> None:
    candidates = [
        _candidate(services, "university-sql"),
        _candidate(services, "mock-weather-fahrenheit"),
    ]
    result = await services.auditor.verify("task", "subgoal", candidates, "corr")

    assert result.overall["university-sql"] is ClaimLabel.verified
    assert result.overall["mock-weather-fahrenheit"] is ClaimLabel.contradicted
    assert result.labels["mock-weather-fahrenheit"][0].label is ClaimLabel.contradicted


def test_drift_injection_uses_the_auditor_detector(services: AppServices) -> None:
    alert = services.auditor.inject_drift("open-meteo-forecast", reason="test drift")

    assert alert is not None
    assert alert.tool_id == "open-meteo-forecast"
    assert alert.provider_id == "open-meteo"
    assert alert.severity == "high"
    assert any("temperature_2m" in reason for reason in alert.reasons)
    assert services.auditor.alerts()
    assert services.trust.get("open-meteo")["contradictions"] >= 1

    assert services.auditor.clear_drift("open-meteo-forecast") is True
    assert services.auditor.alerts() == []


def test_drift_injection_falls_back_for_a_local_tool(services: AppServices) -> None:
    alert = services.auditor.inject_drift("university-sql", reason="local drift")

    assert alert is not None
    assert alert.tool_id == "university-sql"
    assert alert.severity == "high"
    assert services.auditor.clear_drift("university-sql") is True


def test_auditor_api_exposes_catalog_verify_monitor_and_trust(api: TestClient) -> None:
    overview = api.get("/api/auditor")
    assert overview.status_code == 200
    payload = overview.json()
    assert payload["available"] is True
    assert payload["mode"] == "fixture"
    assert payload["catalog_tools"] == 15
    assert {row["app_tool_id"] for row in payload["mappings"]} == set(TOOL_ALIASES)

    verified = api.post("/api/auditor/verify/open-meteo-forecast")
    assert verified.status_code == 200
    result = verified.json()
    assert result["tool_id"] == "open-meteo"
    assert result["app_tool_id"] == "open-meteo-forecast"
    assert result["app_overall"] == "Verified"
    assert result["app_labels"]

    monitored = api.post(
        "/api/auditor/monitor/open-meteo-forecast",
        params={"establish_baseline": "true"},
    )
    assert monitored.status_code == 200
    assert monitored.json()["tool_id"] == "open-meteo"

    trust = api.get("/api/auditor/trust")
    assert trust.status_code == 200
    assert "leaderboard" in trust.json()
    assert api.post("/api/auditor/verify/university-sql").status_code == 404


def test_monitoring_and_demo_routes_include_the_real_auditor(api: TestClient) -> None:
    monitoring = api.get("/api/monitoring").json()
    assert monitoring["auditor"]["available"] is True
    assert monitoring["auditor"]["mapped_tools"] == len(TOOL_ALIASES)

    injected = api.post("/api/demo/drift/open-meteo-forecast")
    assert injected.status_code == 200
    alert = injected.json()["alert"]
    assert alert["tool_id"] == "open-meteo-forecast"
    assert alert["severity"] == "high"

    monitoring = api.get("/api/monitoring").json()
    assert any(item["alert_id"] == alert["alert_id"] for item in monitoring["drift_alerts"])
    assert monitoring["auditor"]["alerts"] >= 1

    assert api.post("/api/demo/reset").status_code == 200
    reset = api.get("/api/monitoring").json()
    assert reset["drift_alerts"] == []
    assert reset["auditor"]["alerts"] == 0
