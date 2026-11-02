from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger("app.mcp.registry")

from app.mcp.client import MCPClient


class MCPScopeError(ValueError, PermissionError):
    """Raised when a tool call is outside the configured scope for a server."""


class MCPServerRegistry:
    def __init__(self) -> None:
        self.clients: dict[str, MCPClient] = {}
        self.scopes: dict[str, list[str] | None] = {}
        self.audit_log: list[dict[str, Any]] = []

    def register(
        self,
        name: str,
        command: list[str] | str | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        scopes: list[str] | None = None,
    ) -> None:
        client = MCPClient(command=command, env=env, url=url)
        self.clients[name] = client
        self.scopes[name] = scopes

    async def start_all(self) -> None:
        for name, client in list(self.clients.items()):
            try:
                await client.start()
            except Exception as exc:
                self._audit(name, "start", {"error": str(exc), "ok": False})
                # keep client but mark failure by removing? keep for per-client handling
                continue
            self._audit(name, "start", {"ok": True})

    async def stop_all(self) -> None:
        for name, client in list(self.clients.items()):
            try:
                await client.stop()
            except Exception:
                pass

    async def discover_tools(self) -> list[dict[str, Any]]:
        out = []
        for name, client in self.clients.items():
            try:
                tools = await client.list_tools()
            except Exception:
                tools = []
            allowed = self.scopes.get(name)
            for t in tools:
                t = dict(t)
                if allowed is not None and t.get("name") not in allowed:
                    continue
                t["_server"] = name
                out.append(t)
        return out

    async def call_tool(self, server: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        client = self.clients.get(server)
        if client is None:
            raise KeyError(server)
        allowed = self.scopes.get(server)
        if allowed is not None and name not in (allowed or []):
            self._audit(server, "call_tool", {"tool": name, "ok": False, "error": "scope denied"})
            logger.warning("MCP tool %s on %s not in allowed scopes", name, server)
            raise MCPScopeError(f"Tool '{name}' is not allowed for server '{server}'")
        started = time.time()
        try:
            result = await client.call_tool(name, arguments)
            self._audit(server, "call_tool", {"tool": name, "ok": True, "duration_ms": (time.time() - started) * 1000})
            logger.info("MCP call %s/%s ok", server, name)
            return result
        except Exception as exc:
            self._audit(server, "call_tool", {"tool": name, "ok": False, "error": str(exc)})
            logger.exception("MCP call %s/%s failed: %s", server, name, exc)
            raise

    def _audit(self, server: str, action: str, details: dict[str, Any]) -> None:
        entry = {"server": server, "action": action, "details": details, "timestamp": time.time()}
        self.audit_log.append(entry)
        logger.info("MCP audit: %s %s %s", server, action, details)
