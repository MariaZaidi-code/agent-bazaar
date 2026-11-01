from __future__ import annotations

import json

import pytest

from app.mcp.server import AgentBazaarMCPServer
from app.services import AppServices


@pytest.fixture
def mcp(services: AppServices) -> AgentBazaarMCPServer:
    return AgentBazaarMCPServer(services)


def _text(response: dict) -> str:
    return response["result"]["content"][0]["text"]


@pytest.mark.asyncio
async def test_mcp_initialize_advertises_capabilities(mcp: AgentBazaarMCPServer) -> None:
    response = await mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})

    assert response is not None
    assert response["result"]["serverInfo"]["name"] == "agent-bazaar-mcp"
    assert set(response["result"]["capabilities"]) == {"tools", "resources", "prompts"}


@pytest.mark.asyncio
async def test_mcp_lists_six_tools(mcp: AgentBazaarMCPServer) -> None:
    response = await mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})

    names = {tool["name"] for tool in response["result"]["tools"]}
    assert names == {
        "run_task",
        "search_tools",
        "get_trace",
        "list_providers",
        "verify_tool",
        "monitor_tool",
    }


@pytest.mark.asyncio
async def test_mcp_lists_and_reads_resources(mcp: AgentBazaarMCPServer) -> None:
    listing = await mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "resources/list"})
    uris = {item["uri"] for item in listing["result"]["resources"]}
    assert uris == {
        "agent-bazaar://ontology",
        "agent-bazaar://graph",
        "agent-bazaar://trust",
    }

    graph = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": "agent-bazaar://graph"},
        }
    )
    tools = json.loads(graph["result"]["contents"][0]["text"])
    assert len(tools) >= 60
    assert {"tool_id", "provider_id", "capability"} <= set(tools[0])


@pytest.mark.asyncio
async def test_mcp_prompts_render_arguments(mcp: AgentBazaarMCPServer) -> None:
    listing = await mcp.handle({"jsonrpc": "2.0", "id": 5, "method": "prompts/list"})
    assert {prompt["name"] for prompt in listing["result"]["prompts"]} == {
        "plan_task",
        "verify_provider",
        "explain_trust",
    }

    rendered = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "prompts/get",
            "params": {"name": "plan_task", "arguments": {"task": "weather in Lahore"}},
        }
    )
    text = rendered["result"]["messages"][0]["content"]["text"]
    assert "weather in Lahore" in text


@pytest.mark.asyncio
async def test_mcp_search_tools_returns_ranked_matches(mcp: AgentBazaarMCPServer) -> None:
    response = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"name": "search_tools", "arguments": {"query": "weather forecast", "limit": 3}},
        }
    )

    matches = json.loads(_text(response))
    assert matches
    assert len(matches) <= 3
    assert all("tool_id" in match and "relevance" in match for match in matches)


@pytest.mark.asyncio
async def test_mcp_lists_providers_with_health(mcp: AgentBazaarMCPServer) -> None:
    response = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "list_providers", "arguments": {}},
        }
    )

    providers = json.loads(_text(response))
    assert len(providers) >= 60
    assert {"provider_id", "tool_id", "mode", "capability"} <= set(providers[0])


@pytest.mark.asyncio
async def test_mcp_verifies_and_monitors_a_known_tool(mcp: AgentBazaarMCPServer) -> None:
    verified = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "verify_tool", "arguments": {"tool_id": "nominatim-geocode"}},
        }
    )
    payload = json.loads(_text(verified))
    assert payload["app_tool_id"] == "nominatim-geocode"

    monitored = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "monitor_tool", "arguments": {"tool_id": "nominatim-geocode"}},
        }
    )
    assert "drift_alerts" in json.loads(_text(monitored))


@pytest.mark.asyncio
async def test_mcp_returns_json_rpc_errors(mcp: AgentBazaarMCPServer) -> None:
    unknown = await mcp.handle({"jsonrpc": "2.0", "id": 11, "method": "unknown/method"})
    assert unknown["error"]["code"] == -32601

    missing = await mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 12,
            "method": "tools/call",
            "params": {"name": "run_task", "arguments": {}},
        }
    )
    assert missing["error"]["code"] == -32603


@pytest.mark.asyncio
async def test_mcp_ignores_notifications(mcp: AgentBazaarMCPServer) -> None:
    assert await mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
