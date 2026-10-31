from __future__ import annotations

import json
from typing import Any


def encode_message(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    return header + body


def decode_message(data: bytes) -> dict[str, Any]:
    # Expect LSP-style framing
    text = data.decode("utf-8", errors="replace")
    if "\r\n\r\n" in text:
        _, body = text.split("\r\n\r\n", 1)
    else:
        body = text
    return json.loads(body)


def make_request(method: str, params: dict[str, Any] | None = None, req_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params or {}}


def make_notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "method": method, "params": params or {}}
