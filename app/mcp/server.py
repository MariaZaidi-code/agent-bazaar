from __future__ import annotations

import asyncio
import json
import sys
from typing import Any

from app.config import Settings
from app.mcp.protocol import encode_message
from app.services import AppServices, build_services

TOOLS: list[dict[str, Any]] = [
    {
        "name": "run_task",
        "description": "Plan, rank and execute a natural-language task with the Agent Bazaar Client agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {"type": "string", "description": "The developer task to run."},
                "document_id": {
                    "type": "string",
                    "description": "Optional uploaded document id for document questions.",
                },
            },
            "required": ["task"],
        },
    },
    {
        "name": "search_tools",
        "description": "Search the provider catalogue with GraphRAG and return ranked tools.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What the tool should do."},
                "capability": {"type": "string", "description": "Optional capability filter."},
                "limit": {"type": "integer", "default": 8},
            },
            "required": ["query"],
        },
    },
    {
        "name": "get_trace",
        "description": "Read the persisted decision trace and final answer for a task.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "list_providers",
        "description": "List every provider with mode, health and capability information.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "verify_tool",
        "description": "Run the Auditor claim verification for one tool.",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_id": {"type": "string"}},
            "required": ["tool_id"],
        },
    },
    {
        "name": "monitor_tool",
        "description": "Run the Auditor drift monitor for one tool.",
        "inputSchema": {
            "type": "object",
            "properties": {"tool_id": {"type": "string"}},
            "required": ["tool_id"],
        },
    },
]

PROMPTS: list[dict[str, Any]] = [
    {
        "name": "plan_task",
        "description": "Template for asking Agent Bazaar to plan and run a task.",
        "arguments": [{"name": "task", "description": "The task to plan.", "required": True}],
    },
    {
        "name": "verify_provider",
        "description": "Template for asking Agent Bazaar to verify a provider.",
        "arguments": [{"name": "tool_id", "description": "Tool id to verify.", "required": True}],
    },
    {
        "name": "explain_trust",
        "description": "Template for explaining a provider trust score in plain language.",
        "arguments": [{"name": "tool_id", "description": "Tool id to explain.", "required": True}],
    },
]

PROMPT_TEMPLATES = {
    "plan_task": (
        "Use the run_task tool to answer this request. "
        "Explain which tools were chosen and why.\n\nTask: {task}"
    ),
    "verify_provider": (
        "Use the verify_tool tool for {tool_id}. Summarise the claim labels and any drift alerts."
    ),
    "explain_trust": (
        "Use list_providers, then explain the trust score for {tool_id} "
        "in plain language with no formulas."
    ),
}


class AgentBazaarMCPServer:
    """In-process MCP server exposing Agent Bazaar tools, resources and prompts."""

    def __init__(self, services: AppServices) -> None:
        self.services = services

    def _tool_result(self, payload: Any) -> dict[str, Any]:
        return {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(payload, ensure_ascii=False, default=str, indent=2),
                }
            ]
        }

    async def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if name == "run_task":
            task = str(arguments.get("task", "")).strip()
            if not task:
                raise ValueError("task is required")
            document_id = arguments.get("document_id")
            result = await self.services.client.run(task, document_id=document_id)
            return self._tool_result(result.model_dump(mode="json"))

        if name == "search_tools":
            query = str(arguments.get("query", "")).strip()
            if not query:
                raise ValueError("query is required")
            limit = int(arguments.get("limit", 8) or 8)
            capability = arguments.get("capability")
            matches = self.services.retriever.search(
                query,
                top_k=max(1, min(limit, 25)),
                capability=str(capability) if capability else None,
            )
            return self._tool_result(
                [
                    {
                        "tool_id": tool.id,
                        "name": tool.name,
                        "provider_id": tool.provider_id,
                        "capability": tool.capability,
                        "relevance": round(score, 4),
                        "reasons": reasons,
                    }
                    for tool, score, reasons in matches
                ]
            )

        if name == "get_trace":
            task_id = str(arguments.get("task_id", "")).strip()
            if not task_id:
                raise ValueError("task_id is required")
            result = self.services.traces.get_result(task_id)
            return self._tool_result(
                {
                    "task_id": task_id,
                    "events": [
                        event.model_dump(mode="json")
                        for event in self.services.traces.events(task_id)
                    ],
                    "result": result.model_dump(mode="json") if result is not None else None,
                }
            )

        if name == "list_providers":
            return self._tool_result(self.services.providers.status())

        if name == "verify_tool":
            tool_id = str(arguments.get("tool_id", "")).strip()
            if not tool_id:
                raise ValueError("tool_id is required")
            return self._tool_result(self.services.auditor.verify_tool(tool_id))

        if name == "monitor_tool":
            tool_id = str(arguments.get("tool_id", "")).strip()
            if not tool_id:
                raise ValueError("tool_id is required")
            return self._tool_result(self.services.auditor.monitor_tool(tool_id))

        raise KeyError(f"unknown tool: {name}")

    def _resource_payload(self, uri: str) -> str:
        if uri == "agent-bazaar://ontology":
            ontology = self.services.ontology
            capabilities = getattr(ontology, "capabilities", {})
            concepts = getattr(ontology, "concepts", {})
            return json.dumps(
                {"capabilities": capabilities, "concepts": sorted(concepts)},
                ensure_ascii=False,
                default=str,
                indent=2,
            )
        if uri == "agent-bazaar://graph":
            return json.dumps(
                [
                    {
                        "tool_id": tool.id,
                        "name": tool.name,
                        "provider_id": tool.provider_id,
                        "capability": tool.capability,
                    }
                    for tool in self.services.graph.all()
                ],
                ensure_ascii=False,
                indent=2,
            )
        if uri == "agent-bazaar://trust":
            return json.dumps(self.services.trust.all(), ensure_ascii=False, default=str, indent=2)
        raise KeyError(f"unknown resource: {uri}")

    async def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method", "")
        request_id = request.get("id")
        params = request.get("params") or {}
        if method.startswith("notifications/"):
            return None
        try:
            if method == "initialize":
                result: Any = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {"listChanged": False},
                        "resources": {"listChanged": False},
                        "prompts": {"listChanged": False},
                    },
                    "serverInfo": {"name": "agent-bazaar-mcp", "version": "1.0"},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                result = await self._call_tool(
                    str(params.get("name", "")), params.get("arguments") or {}
                )
            elif method == "resources/list":
                result = {
                    "resources": [
                        {
                            "uri": "agent-bazaar://ontology",
                            "name": "Ontology",
                            "description": "Capabilities and concepts used for validation.",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "agent-bazaar://graph",
                            "name": "Tool graph",
                            "description": "Provider tools and their capabilities.",
                            "mimeType": "application/json",
                        },
                        {
                            "uri": "agent-bazaar://trust",
                            "name": "Trust ledger",
                            "description": "Current trust scores and signal history.",
                            "mimeType": "application/json",
                        },
                    ]
                }
            elif method == "resources/read":
                uri = str(params.get("uri", ""))
                result = {
                    "contents": [
                        {
                            "uri": uri,
                            "mimeType": "application/json",
                            "text": self._resource_payload(uri),
                        }
                    ]
                }
            elif method == "prompts/list":
                result = {"prompts": PROMPTS}
            elif method == "prompts/get":
                name = str(params.get("name", ""))
                template = PROMPT_TEMPLATES.get(name)
                if template is None:
                    raise KeyError(f"unknown prompt: {name}")
                arguments = params.get("arguments") or {}
                rendered = template.format(
                    task=arguments.get("task", ""),
                    tool_id=arguments.get("tool_id", ""),
                )
                result = {
                    "description": next(
                        (prompt["description"] for prompt in PROMPTS if prompt["name"] == name), ""
                    ),
                    "messages": [
                        {"role": "user", "content": {"type": "text", "text": rendered}}
                    ],
                }
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"method not found: {method}"},
                }
        except KeyError as error:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32602, "message": str(error)},
            }
        except Exception as error:  # noqa: BLE001
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32603, "message": str(error)},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _read_message(stream: Any) -> dict[str, Any] | None:
    headers = b""
    while b"\r\n\r\n" not in headers:
        chunk = stream.read(1)
        if not chunk:
            return None
        headers += chunk
    content_length = 0
    for line in headers.split(b"\r\n"):
        if line.lower().startswith(b"content-length:"):
            content_length = int(line.split(b":", 1)[1].strip())
    body = stream.read(content_length)
    if not body:
        return None
    return json.loads(body)


async def serve(services: AppServices) -> None:
    server = AgentBazaarMCPServer(services)
    stream = sys.stdin.buffer
    out = sys.stdout.buffer
    while True:
        request = _read_message(stream)
        if request is None:
            break
        response = await server.handle(request)
        if response is not None:
            out.write(encode_message(response))
            out.flush()


def main() -> None:
    services = build_services(Settings())
    asyncio.run(serve(services))


if __name__ == "__main__":
    main()
