from __future__ import annotations

from fastapi.testclient import TestClient


def run_task(api: TestClient) -> dict:
    response = api.post(
        "/api/tasks",
        json={"task": "What is 25 USD in PKR, and what is the temperature in Lahore?"},
    )
    assert response.status_code == 200
    return response.json()


def test_account_workspace_and_settings(api: TestClient) -> None:
    assert api.get("/api/auth/me").json()["authenticated"] is False
    registered = api.post(
        "/api/auth/register",
        json={
            "email": "qaim@example.com",
            "password": "correct-horse",
            "display_name": "Qaim",
            "workspace_name": "Qaim Studio",
        },
    )
    assert registered.status_code == 200
    payload = registered.json()
    assert payload["authenticated"] is True
    assert payload["user"]["email"] == "qaim@example.com"
    assert payload["workspace"]["name"] == "Qaim Studio"
    assert api.get("/api/auth/me").json()["authenticated"] is True

    created = api.post("/api/workspaces", json={"name": "Client work"})
    assert created.status_code == 200
    assert len(created.json()["workspaces"]) >= 2

    updated = api.put(
        "/api/platform/settings",
        json={"theme": "light", "high_contrast": True, "notifications": False},
    )
    assert updated.status_code == 200
    assert updated.json()["settings"]["theme"] == "light"
    assert updated.json()["settings"]["high_contrast"] is True

    signed_out = api.post("/api/auth/logout")
    assert signed_out.status_code == 200
    assert api.get("/api/auth/me").json()["authenticated"] is False
    signed_in = api.post(
        "/api/auth/login",
        json={"email": "qaim@example.com", "password": "correct-horse"},
    )
    assert signed_in.status_code == 200
    assert signed_in.json()["authenticated"] is True


def test_saved_work_shares_and_exports(api: TestClient) -> None:
    result = run_task(api)
    tools = result["plan"]["steps"]
    tool_id = tools[0]["tool_id"]

    favorite = api.post("/api/favorites", json={"tool_id": tool_id, "note": "Useful", "tags": "money"})
    assert favorite.status_code == 200
    favorites = api.get("/api/favorites").json()["favorites"]
    assert favorites[0]["tool_id"] == tool_id
    assert favorites[0]["tags"] == "money"

    saved = api.post("/api/saved-tasks", json={"task_id": result["task_id"], "title": "Currency check"})
    assert saved.status_code == 200
    assert api.get("/api/saved-tasks").json()["saved_tasks"][0]["title"] == "Currency check"

    workflow = api.post(
        "/api/workflows",
        json={"name": "Weekly check", "task": result["task"], "plan": {"steps": tools}},
    )
    assert workflow.status_code == 200
    workflows = api.get("/api/workflows").json()["workflows"]
    assert workflows[0]["name"] == "Weekly check"
    assert workflows[0]["plan"]["steps"] == tools

    recent = api.get("/api/tasks/recent", params={"q": "PKR"}).json()
    assert recent["total"] >= 1

    shared = api.post(f"/api/tasks/{result['task_id']}/share")
    assert shared.status_code == 200
    url = shared.json()["url"]
    token = shared.json()["token"]
    assert url.endswith(f"/share/{token}")
    shared_page = api.get(f"/share/{token}")
    assert shared_page.status_code == 200
    assert "Read-only shared answer" in shared_page.text

    formats = (
        ("json", "application/json"),
        ("csv", "text/csv"),
        ("md", "text/markdown"),
        ("pdf", "application/pdf"),
    )
    for fmt, media in formats:
        exported = api.get(f"/api/tasks/{result['task_id']}/export", params={"format": fmt})
        assert exported.status_code == 200
        assert exported.headers["content-type"].startswith(media)
    assert api.get(f"/api/tasks/{result['task_id']}/export", params={"format": "xml"}).status_code == 400


def test_notifications_credentials_and_admin(api: TestClient) -> None:
    result = run_task(api)
    notifications = api.get("/api/notifications").json()
    assert notifications["unread"] >= 1
    assert api.post("/api/notifications/read", json={"ids": []}).json()["updated"] >= 1

    key = api.post("/api/api-keys", json={"provider": "example", "key": "secret-value-1234"})
    assert key.status_code == 200
    keys = key.json()["keys"]
    assert keys[0]["provider"] == "example"
    assert keys[0]["masked"].endswith("1234")
    assert "secret-value" not in str(keys)

    flags = api.get("/api/admin/flags").json()["flags"]
    assert flags
    updated = api.put(f"/api/admin/flags/{flags[0]['name']}", json={"enabled": not flags[0]["enabled"]})
    assert updated.status_code == 200
    assert updated.json()["enabled"] is not flags[0]["enabled"]

    webhook = api.post("/api/webhooks", json={"url": "https://example.com/hook", "event": "*"})
    assert webhook.status_code == 200
    assert api.get("/api/webhooks").json()["webhooks"][0]["url"] == "https://example.com/hook"

    schedule = api.post("/api/schedules", json={"task": "Check currency rates", "cadence": "hourly"})
    assert schedule.status_code == 200
    assert api.get("/api/schedules").json()["schedules"][0]["cadence"] == "hourly"

    override = api.put(
        "/api/admin/overrides",
        json={"tool_id": result["plan"]["steps"][0]["tool_id"], "field_name": "pricing_tier", "value": "free"},
    )
    assert override.status_code == 200
    assert api.get("/api/admin/overrides").json()["overrides"][0]["value"] == "free"

    analytics = api.get("/api/analytics").json()
    assert analytics["totals"]["tasks"] >= 1
    assert analytics["top_tools"]
    assert api.get("/api/audit").json()["entries"]
    assert api.get("/api/cache").status_code == 200
    assert api.delete("/api/cache").status_code == 200

    exported = api.get("/api/workspace/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].startswith("attachment")
    imported = api.post(
        "/api/workspace/import",
        json={"favorites": [{"tool_id": result["plan"]["steps"][0]["tool_id"], "note": "Imported"}]},
    )
    assert imported.status_code == 200
    assert imported.json()["imported"]["favorites"] == 1
