from __future__ import annotations

from typing import Any

from app.mcp.client import MCPClient


class MCPServerRegistry:
    def __init__(self) -> None:
        self.clients: dict[str, MCPClient] = {}

    def register(self, name: str, command: list[str], env: dict[str, str] | None = None) -> None:
        self.clients[name] = MCPClient(command, env)

    async def start_all(self) -> None:
        for client in self.clients.values():
            await client.start()

    async def stop_all(self) -> None:
        for client in self.clients.values():
            await client.stop()

    async def discover_tools(self) -> list[dict[str, Any]]:
        out = []
        for name, client in self.clients.items():
            try:
                tools = await client.list_tools()
            except Exception:
                tools = []
            for t in tools:
                t = dict(t)
                t["_server"] = name
                out.append(t)
        return out

    async def call_tool(self, server: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        client = self.clients.get(server)
        if client is None:
            raise KeyError(server)
        return await client.call_tool(name, arguments)
