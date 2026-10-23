from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_and_interface(api: TestClient) -> None:
    health = api.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["mode"] == "offline"
    assert health["tools"] >= 10
    assert api.get("/").status_code == 200
    assert "Agent Bazaar" in api.get("/").text
    pages = {
        "/dashboard": "Workflow workspace",
        "/marketplace": "Service marketplace",
        "/monitor": "Self-healing monitor",
        "/library": "Interface library",
    }
    for path, title in pages.items():
        response = api.get(path)
        assert response.status_code == 200
        assert f"<title>{title} | Agent Bazaar</title>" in response.text
        assert f'data-page="{path.removeprefix("/")}"' in response.text
    assert api.get("/static/styles.css").status_code == 200
    assert api.get("/static/app.js").status_code == 200
    assert api.get("/favicon.ico").status_code == 204


def test_task_lifecycle(api: TestClient) -> None:
    task = "What is the temperature in Lahore tomorrow, and what is 200 USD in PKR?"
    response = api.post("/api/tasks", json={"task": task})
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "completed"
    assert result["task_id"].startswith("task_")
    assert result["trace"]
    task_id = result["task_id"]

    fetched = api.get(f"/api/tasks/{task_id}")
    assert fetched.status_code == 200
    assert fetched.json()["answer"] == result["answer"]
    assert api.get("/api/tasks/recent").status_code == 200
    assert api.get(f"/api/tasks/{task_id}/messages").status_code == 200
    assert api.get("/api/tasks/task_missing").status_code == 404


def test_tools_ontology_and_monitoring(api: TestClient) -> None:
    tools = api.get("/api/tools").json()
    assert tools["count"] == len(tools["tools"])
    assert any(tool["id"] == "open-meteo-forecast" for tool in tools["tools"])

    ontology = api.get("/api/ontology").json()
    assert "Coordinates" in {concept["concept"] for concept in ontology["concepts"]}
    assert "GetWeatherForecast" in ontology["capabilities"]

    monitoring = api.get("/api/monitoring").json()
    assert monitoring["mode"] == "offline"
    assert monitoring["providers"]
    assert isinstance(monitoring["breakers"], list)


def test_demo_failure_drift_and_reset(api: TestClient) -> None:
    scheduled = api.post("/api/demo/fail-next/open-meteo-forecast", json={"times": 1})
    assert scheduled.status_code == 200
    result = api.post("/api/tasks", json={"task": "What is the temperature in Lahore tomorrow?"}).json()
    weather = next(step for step in result["plan"]["steps"] if step["capability"] == "GetWeatherForecast")
    assert weather["substituted_from"] == "open-meteo-forecast"

    drift = api.post("/api/demo/drift/open-meteo-forecast")
    assert drift.status_code == 200
    monitoring = api.get("/api/monitoring").json()
    assert any(item["tool_id"] == "open-meteo-forecast" for item in monitoring["drift_alerts"])
    assert any(item["state"] == "open" for item in monitoring["breakers"])

    assert api.post("/api/demo/trip/nominatim-geocode").status_code == 200
    assert api.post("/api/demo/reset").status_code == 200
    reset = api.get("/api/monitoring").json()
    assert reset["drift_alerts"] == []
    assert reset["breakers"] == []


def test_document_upload_and_question(api: TestClient) -> None:
    upload = api.post(
        "/api/documents",
        files={"file": ("facts.txt", b"The demo capital is Lahore. The demo has forty two tools.", "text/plain")},
    )
    assert upload.status_code == 200
    assert upload.json()["document"]["name"] == "facts.txt"
    assert api.get("/api/documents").json()["documents"]

    result = api.post(
        "/api/tasks",
        json={"task": "According to the uploaded document, what is the demo capital?"},
    ).json()
    assert result["status"] == "completed"
    assert "Lahore" in result["answer"]


def test_corrections_listings_and_baselines(api: TestClient) -> None:
    accepted = api.post(
        "/api/corrections",
        json={
            "tool_id": "mock-weather-fahrenheit",
            "field_name": "forecast",
            "original_concept": "Temperature",
            "corrected_concept": "Temperature",
            "corrected_unit": "C",
            "note": "Normalize units.",
        },
    )
    assert accepted.status_code == 200
    assert accepted.json()["accepted"] is True
    assert api.get("/api/staged").json()["corrections"]

    rejected = api.post(
        "/api/corrections",
        json={
            "tool_id": "open-meteo-forecast",
            "field_name": "coordinates",
            "original_concept": "UnknownConcept",
            "corrected_concept": "Coordinates",
        },
    )
    assert rejected.json()["accepted"] is False

    listing = api.post(
        "/api/listings",
        json={
            "name": "Demo News Search",
            "description": "Search recent news headlines.",
            "capability": "SearchResearchPapers",
            "inputs": [{"concept": "ResearchTopic", "name": "query"}],
            "outputs": [{"concept": "ResearchPaper", "name": "papers"}],
        },
    )
    assert listing.status_code == 200
    assert "staged" in listing.json() or "accepted" in listing.json()

    for name in ("b1", "b2"):
        baseline = api.post(f"/api/baselines/{name}", json={"task": "How many students are enrolled?"})
        assert baseline.status_code == 200
        assert name in baseline.json()["baseline"].lower()
    assert api.post("/api/baselines/b3", json={"task": "test task"}).status_code == 404
    assert api.get("/api/evaluations").status_code == 200
