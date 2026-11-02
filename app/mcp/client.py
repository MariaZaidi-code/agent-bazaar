from __future__ import annotations

import asyncio
import hashlib
import json
import os
import subprocess
import time
from typing import Any
from urllib.parse import urlparse

import httpx

from app.mcp.protocol import encode_message, make_notification, make_request

ALLOWED_ENV_KEYS = {
    "PATH",
    "HOME",
    "USER",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "PYTHONPATH",
    "SYSTEMROOT",
    "COMSPEC",
    "TEMP",
    "TMP",
}


class MCPClient:
    def __init__(
        self,
        command: list[str] | str | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        timeout: float = 30.0,
        read_timeout: float | None = None,
        allowed_env: set[str] | None = None,
    ) -> None:
        if url is None and isinstance(command, str) and command.startswith(("http://", "https://")):
            url = command
            command = None
        if url is None and isinstance(command, list) and len(command) == 1 and isinstance(command[0], str) and command[0].startswith(("http://", "https://")):
            url = command[0]
            command = None
        self.command = command
        self.url = url
        self.env = env or {}
        self.timeout = timeout
        self.read_timeout = read_timeout if read_timeout is not None else timeout
        self.allowed_env = allowed_env if allowed_env is not None else ALLOWED_ENV_KEYS
        self.process: subprocess.Popen | None = None
        self._req_id = 0
        self._lock = asyncio.Lock()
        self._sse_client: httpx.AsyncClient | None = None
        self._post_url: str | None = None

    def _build_env(self) -> dict[str, str]:
        base = {key: os.environ[key] for key in self.allowed_env if key in os.environ}
        base.update(self.env)
        return base

    async def start(self) -> None:
        if self.url:
            self._sse_client = httpx.AsyncClient(timeout=self.read_timeout)
            # Try to obtain endpoint via SSE handshake is optional; default to url.
            self._post_url = self.url
            await self._request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "agent-bazaar", "version": "1.0"},
                },
            )
            await self._notify("notifications/initialized", {})
            return
        if not self.command:
            raise RuntimeError("MCP command or URL required")
        self.process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=self._build_env(),
        )
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
        if self.url:
            assert self._sse_client is not None
            async with self._lock:
                self._req_id += 1
                req_id = self._req_id
                req = make_request(method, params, req_id)
                try:
                    resp = await self._sse_client.post(self._post_url or self.url, json=req, timeout=self.read_timeout)
                    data = resp.json()
                except Exception as exc:
                    raise RuntimeError(f"MCP request failed: {exc}") from exc
                if data.get("id") != req_id:
                    raise RuntimeError("MCP id correlation mismatch")
                if "error" in data:
                    raise RuntimeError(str(data["error"]))
                return data
        if self.process is None or self.process.stdin is None or self.process.stdout is None:
            raise RuntimeError("MCP process not started")
        async with self._lock:
            self._req_id += 1
            req_id = self._req_id
            req = make_request(method, params, req_id)
            self.process.stdin.write(encode_message(req))
            self.process.stdin.flush()
            loop = asyncio.get_event_loop()
            try:
                data = await asyncio.wait_for(loop.run_in_executor(None, self._read_one), timeout=self.read_timeout)
            except asyncio.TimeoutError as exc:
                raise RuntimeError("MCP read timeout") from exc
            if data.get("id") != req_id:
                raise RuntimeError("MCP id correlation mismatch")
            if "error" in data:
                raise RuntimeError(str(data["error"]))
            return data

    def _read_one(self) -> dict[str, Any]:
        assert self.process is not None and self.process.stdout is not None
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
        if self.url:
            if self._sse_client is None:
                return
            try:
                await self._sse_client.post(
                    self._post_url or self.url, json=make_notification(method, params), timeout=self.read_timeout
                )
            except Exception:
                return
            return
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
        if self._sse_client is not None:
            try:
                await self._sse_client.aclose()
            except Exception:
                pass
            self._sse_client = None
        proc = self.process
        self.process = None
        if proc is not None:
            for stream in (proc.stdin, proc.stdout, proc.stderr):
                try:
                    if stream is not None:
                        stream.close()
                except Exception:
                    pass
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=5)
                except Exception:
                    pass
