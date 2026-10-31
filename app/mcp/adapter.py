from __future__ import annotations

from typing import Any

from app.mcp.registry import MCPServerRegistry
from app.providers.base import BaseProvider
from app.schemas import ConceptSpec, ToolSpec


def mcp_tool_to_spec(server: str, tool: dict[str, Any]) -> ToolSpec:
    name = tool.get("name", "")
    description = tool.get("description", "")
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    required = set(schema.get("required") or [])
    inputs = []
    for key, spec in props.items():
        inputs.append(
            ConceptSpec(concept="Text", name=key, required=key in required, description=spec.get("description", ""))
        )
    if not inputs:
        inputs = [ConceptSpec(concept="Text", name="query", required=False)]
    outputs = [ConceptSpec(concept="Text", name="result")]
    return ToolSpec(
        id=f"mcp-{server}-{name}",
        name=f"{name} (MCP:{server})",
        provider_id=f"mcp-{server}",
        description=description or f"MCP tool {name}",
        capability=f"MCP_{name}",
        inputs=inputs,
        outputs=outputs,
        keywords=[name, server, "mcp"],
        price=0.0,
        pricing_tier="free",
        access_requirement="keyless",
        licence="unknown",
        is_executable=True,
        probe_eligible=False,
        execution="live",
        tags=["mcp"],
    )


class MCPToolProvider(BaseProvider):
    def __init__(self, spec, settings, cache, registry: MCPServerRegistry, server: str, tool_name: str) -> None:
        super().__init__(spec, settings, cache)
        self.registry = registry
        self.server = server
        self.tool_name = tool_name

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        result = await self.registry.call_tool(self.server, self.tool_name, params)
        content = result.get("content") if isinstance(result, dict) else None
        if isinstance(content, list):
            text_parts = [c.get("text", "") for c in content if isinstance(c, dict)]
            return {"result": "\n".join(text_parts) if text_parts else result}
        return result if isinstance(result, dict) else {"result": result}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"result": "offline (MCP server unavailable)"}
