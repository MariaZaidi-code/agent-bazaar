from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings


@dataclass
class McpServerConfig:
    id: str
    name: str
    url: str
    transport: str = "http"
    scopes: list[str] = field(default_factory=lambda: ["tools:read", "tools:execute"])
    enabled: bool = True


@dataclass
class McpTool:
    server_id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class McpManager:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._servers: dict[str, McpServerConfig] = {}
        self._tools: dict[str, list[McpTool]] = {}
        self._lock = threading.RLock()
        self._audit_path = settings.runtime_dir / "mcp_audit.jsonl"
        self.settings.runtime_dir.mkdir(parents=True, exist_ok=True)
        self._load_config()

    def _load_config(self) -> None:
        path = self.settings.runtime_dir.parent / "mcp_servers.yaml"
        # Also allow the conventional project-level gitignored file.
        candidates = [path, Path("config/mcp_servers.yaml"), Path("mcp_servers.yaml")]
        for candidate in candidates:
            if candidate.exists():
                try:
                    import yaml

                    raw = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
                except Exception:
                    raw = {}
                for item in raw.get("servers", []) if isinstance(raw, dict) else []:
                    if not isinstance(item, dict) or not item.get("id") or not item.get("url"):
                        continue
                    config = McpServerConfig(
                        id=str(item["id"]),
                        name=str(item.get("name", item["id"])),
                        url=str(item["url"]).rstrip("/"),
                        transport=str(item.get("transport", "http")),
                        scopes=[str(scope) for scope in item.get("scopes", ["tools:read", "tools:execute"])],
                        enabled=bool(item.get("enabled", True)),
                    )
                    self._servers[config.id] = config
        if "local" not in self._servers:
            self._servers["local"] = McpServerConfig(
                id="local",
                name="Local Agent Bazaar",
                url="",
                transport="local",
                scopes=["tools:read", "tools:execute", "resources:read", "prompts:read"],
            )

    def servers(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    "id": server.id,
                    "name": server.name,
                    "url": server.url,
                    "transport": server.transport,
                    "scopes": server.scopes,
                    "enabled": server.enabled,
                }
                for server in self._servers.values()
            ]

    def _rpc(self, server: McpServerConfig, method: str, params: dict[str, Any] | None = None) -> Any:
        if server.transport == "local":
            raise ValueError("local server does not use JSON-RPC")
        payload = {"jsonrpc": "2.0", "id": int(time.time() * 1000), "method": method, "params": params or {}}
        with httpx.Client(timeout=15.0) as client:
            response = client.post(server.url, json=payload)
            response.raise_for_status()
            data = response.json()
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(str(data["error"]))
        return data.get("result") if isinstance(data, dict) else data

    def discover(self, server_id: str) -> list[dict[str, Any]]:
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if not server.enabled:
            raise ValueError(f"MCP server is disabled: {server_id}")
        if server.transport == "local":
            tools = []
            for provider in []:  # populated by the app layer through register_local_tools
                tools.append(provider)
            tools = self._tools.get(server_id, [])
        else:
            result = self._rpc(server, "tools/list", {})
            raw_tools = result.get("tools", []) if isinstance(result, dict) else []
            tools = [
                McpTool(
                    server_id=server_id,
                    name=str(item.get("name", "")),
                    description=str(item.get("description", "")),
                    input_schema=dict(item.get("inputSchema", {}) or {}),
                )
                for item in raw_tools
                if isinstance(item, dict) and item.get("name")
            ]
            with self._lock:
                self._tools[server_id] = tools
        self._audit("discover", server_id, {"tool_count": len(self._tools.get(server_id, []))})
        return [tool.to_dict() for tool in self._tools.get(server_id, [])]

    def register_local_tools(self, tools: list[McpTool]) -> None:
        with self._lock:
            self._tools["local"] = tools

    def tools(self, server_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock:
            if server_id is not None:
                return [tool.to_dict() for tool in self._tools.get(server_id, [])]
            result = []
            for tools in self._tools.values():
                result.extend(tool.to_dict() for tool in tools)
            return result

    async def call(self, server_id: str, tool_name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if "tools:execute" not in server.scopes:
            raise PermissionError(f"Server {server_id} does not allow tool execution")
        arguments = arguments or {}
        if server.transport == "local":
            tool = next((item for item in self._tools.get(server_id, []) if item.name == tool_name), None)
            if tool is None:
                raise ValueError(f"Unknown local MCP tool: {tool_name}")
            handler = getattr(tool, "handler", None)
            if not callable(handler):
                raise ValueError(f"Local MCP tool has no handler: {tool_name}")
            started = time.perf_counter()
            try:
                import asyncio

                result = await asyncio.to_thread(handler, arguments)
                status = "success"
                error = None
            except Exception as exc:  # pragma: no cover - defensive boundary
                result = None
                status = "error"
                error = str(exc)
            self._audit(
                "call",
                server_id,
                {
                    "tool": tool_name,
                    "status": status,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                    "error": error,
                },
            )
            if status == "error":
                raise RuntimeError(error or "MCP tool failed")
            return {"server_id": server_id, "tool": tool_name, "result": result}
        payload = {"name": tool_name, "arguments": arguments}
        import asyncio

        result = await asyncio.to_thread(self._rpc, server, "tools/call", payload)
        self._audit("call", server_id, {"tool": tool_name, "status": "success"})
        return {"server_id": server_id, "tool": tool_name, "result": result}

    def resources(self, server_id: str) -> list[dict[str, Any]]:
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if server.transport == "local":
            return [
                {"uri": "agent-bazaar://ontology", "name": "ontology", "description": "Ontology summary"},
                {"uri": "agent-bazaar://graph", "name": "graph", "description": "Knowledge graph statistics"},
                {"uri": "agent-bazaar://trust", "name": "trust", "description": "Trust leaderboard"},
            ]
        result = self._rpc(server, "resources/list", {})
        return result.get("resources", []) if isinstance(result, dict) else []

    def prompts(self, server_id: str) -> list[dict[str, Any]]:
        server = self._servers.get(server_id)
        if server is None:
            raise ValueError(f"Unknown MCP server: {server_id}")
        if server.transport == "local":
            return [
                {"name": "task_decomposition", "description": "Decompose a user task into sub-goals"},
                {"name": "tool_verification", "description": "Verify a tool against its documentation"},
            ]
        result = self._rpc(server, "prompts/list", {})
        return result.get("prompts", []) if isinstance(result, dict) else []

    def read_resource(self, name: str, services: Any) -> dict[str, Any]:
        if name == "ontology":
            return {"name": name, "data": services.ontology.summary() if hasattr(services.ontology, "summary") else {}}
        if name == "graph":
            return {"name": name, "data": services.graph.all() and {"tools": len(services.graph.all())}}
        if name == "trust":
            return {"name": name, "data": services.trust.all()}
        raise ValueError(f"Unknown resource: {name}")

    def _audit(self, action: str, server_id: str, details: dict[str, Any]) -> None:
        record = {"timestamp": time.time(), "action": action, "server_id": server_id, "details": details}
        with self._lock:
            with self._audit_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, default=str) + "\n")

    def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        if not self._audit_path.exists():
            return []
        lines = self._audit_path.read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines if line.strip()]
        return records[-limit:]
