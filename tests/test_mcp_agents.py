from __future__ import annotations

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_mcp_and_agents(tmp_path) -> None:
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    with TestClient(create_app(settings)) as api:
        servers = api.get("/api/mcp/servers").json()["servers"]
        assert any(server["id"] == "local" for server in servers)
        discovered = api.post("/api/mcp/discover/local").json()["tools"]
        assert discovered
        tool_name = discovered[0]["name"]
        response = api.post("/api/mcp/call", json={"server_id": "local", "tool": tool_name, "arguments": {}})
        assert response.status_code == 200
        resources = api.get("/api/mcp/resources").json()["resources"]
        assert {resource["name"] for resource in resources} == {"ontology", "graph", "trust"}
        assert api.get("/api/mcp/prompts").status_code == 200
        assert api.get("/api/mcp/audit").status_code == 200
        rpc = api.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        assert rpc.status_code == 200 and "result" in rpc.json()

        agents = api.get("/api/agents").json()["agents"]
        assert len(agents) == 8
        assert api.post("/api/agents/planner/run", json={}).status_code == 200


def test_provider_health_and_selection(tmp_path) -> None:
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime", rate_limit_enabled=False)
    with TestClient(create_app(settings)) as api:
        health = api.get("/api/providers/health").json()["providers"]
        assert health and "health" in health[0]
        selection = api.get("/api/providers/select", params={"capability": health[0]["capability"]}).json()
        assert selection["selected"] == health[0]["provider_id"]
