from __future__ import annotations

import asyncio
import json
import subprocess
from typing import Any

from app.mcp.protocol import encode_message, make_notification, make_request


class MCPClient:
    def __init__(self, command: list[str], env: dict[str, str] | None = None) -> None:
        self.command = command
        self.env = env or {}
        self.process: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**dict(__import__("os").environ), **self.env},
        )
        # initialize
        await self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "agent-bazaar", "version": "1.0"},
            },
        )
        await self._notify("notifications/initialized", {})

    async def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("MCP process not started")
        async with self._lock:
            self._req_id += 1
            req = make_request(method, params, self._req_id)
            self.process.stdin.write(encode_message(req))
            self.process.stdin.flush()
            # read response
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._read_one)
            return data

    def _read_one(self) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
        # read headers
        headers = b""
        while b"\r\n\r\n" not in headers:
            chunk = self.process.stdout.read(1)
            if not chunk:
                raise RuntimeError("MCP process closed")
            headers += chunk
        content_length = 0
        for line in headers.split(b"\r\n"):
            if line.lower().startswith(b"content-length:"):
                content_length = int(line.split(b":", 1)[1].strip())
        body = self.process.stdout.read(content_length)
        return json.loads(body)

    async def _notify(self, method: str, params: dict[str, Any]) -> None:
        if self.process is None or self.process.stdin is None:
            return
        msg = make_notification(method, params)
        self.process.stdin.write(encode_message(msg))
        self.process.stdin.flush()

    async def list_tools(self) -> list[dict[str, Any]]:
        resp = await self._request("tools/list", {})
        return resp.get("result", {}).get("tools", [])

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        resp = await self._request("tools/call", {"name": name, "arguments": arguments})
        return resp.get("result", {})

    async def stop(self) -> None:
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except Exception:
                self.process.kill()
            self.process = None
