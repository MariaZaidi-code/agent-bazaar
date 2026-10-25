from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from . import __version__
from .auditor import Auditor
from .claims import Claim
from .mocks.registry import MockRegistry


class AuditorRequestHandler(BaseHTTPRequestHandler):
    server_version = f"AgentBazaarAuditor/{__version__}"

    @property
    def auditor(self) -> Auditor:
        return self.server.auditor  # type: ignore[attr-defined]

    @property
    def mock_registry(self) -> MockRegistry | None:
        return self.server.mock_registry  # type: ignore[attr-defined]

    def _send(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def do_OPTIONS(self) -> None:
        self._send(HTTPStatus.NO_CONTENT, {})

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/health":
                self._send(
                    HTTPStatus.OK,
                    {
                        "status": "ok",
                        "version": __version__,
                        "offline_fixtures": not self.auditor.harness.live,
                        "tools": len(self.auditor.catalog),
                        "probe_definitions": len(self.auditor.definitions),
                        "baselines": self.auditor.monitor.store.count(),
                        "trust_observations": sum(entry.observations for entry in self.auditor.trust_ledger.tools.values()),
                    },
                )
                return
            if path == "/tools":
                self._send(
                    HTTPStatus.OK,
                    {
                        "tools": [
                            {
                                "tool_id": tool.tool_id,
                                "name": tool.name,
                                "category": tool.category,
                                "claim_count": len(tool.claims),
                                "probeable": tool.tool_id in self.auditor.definitions,
                            }
                            for tool in self.auditor.catalog.values()
                        ]
                    },
                )
                return
            if path == "/probes":
                self._send(
                    HTTPStatus.OK,
                    {"probes": [definition.to_dict() for definition in self.auditor.definitions.values()]},
                )
                return
            if path == "/trust":
                self._send(
                    HTTPStatus.OK,
                    {
                        "leaderboard": self.auditor.trust_snapshot(),
                        "feed": self.auditor.trust_feed.summary(),
                    },
                )
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": f"unknown path {path}"})
        except Exception as error:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            payload = self._read_json()
            if path == "/verify" or path == "/monitor":
                result = self._handle_verify(payload, monitoring=path == "/monitor")
                self._send(HTTPStatus.OK, {"result": result.to_dict()})
                return
            if path == "/probe":
                tool_id = str(payload.get("tool_id", ""))
                probe = self.auditor.probe(tool_id, force_live=bool(payload.get("force_live", False)))
                self._send(HTTPStatus.OK, {"probe": probe.to_dict()})
                return
            if path == "/mock":
                if self.mock_registry is None:
                    self._send(HTTPStatus.NOT_IMPLEMENTED, {"error": "mock control is not enabled"})
                    return
                tool_id = str(payload["tool_id"])
                behavior = str(payload.get("behavior", "normal"))
                options = payload.get("options") or {}
                provider = self.mock_registry.control(tool_id, behavior, **options)
                self._send(HTTPStatus.OK, {"mock": provider.state()})
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": f"unknown path {path}"})
        except KeyError as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": f"missing or unknown field: {error}"})
        except (ValueError, TypeError) as error:
            self._send(HTTPStatus.BAD_REQUEST, {"error": str(error)})
        except Exception as error:
            self._send(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(error)})

    def _handle_verify(self, payload: dict[str, Any], monitoring: bool):
        tool_id = str(payload.get("tool_id", ""))
        if not tool_id:
            raise ValueError("tool_id is required")
        claims = None
        if payload.get("claims"):
            claims = [Claim.from_dict(item) for item in payload["claims"]]
        correlation_id = str(payload.get("correlation_id", ""))
        force_live = bool(payload.get("force_live", False))
        if monitoring:
            return self.auditor.monitor_tool(
                tool_id,
                probe_round=int(payload.get("round", 1)),
                force_live=force_live,
                establish_baseline=bool(payload.get("establish_baseline", False)),
            )
        return self.auditor.verify(
            tool_id,
            claims=claims,
            correlation_id=correlation_id,
            reprobe_round=int(payload.get("round", 0)),
            force_live=force_live,
            establish_baseline=bool(payload.get("establish_baseline", True)),
        )

    def log_message(self, format: str, *args: Any) -> None:
        print(f"[auditor-api] {self.address_string()} {format % args}")


class AuditorHTTPServer(ThreadingHTTPServer):
    def __init__(
        self,
        server_address: tuple[str, int],
        auditor: Auditor,
        mock_registry: MockRegistry | None = None,
    ) -> None:
        super().__init__(server_address, AuditorRequestHandler)
        self.auditor = auditor
        self.mock_registry = mock_registry


def create_server(
    auditor: Auditor,
    host: str = "127.0.0.1",
    port: int = 8765,
    mock_registry: MockRegistry | None = None,
) -> AuditorHTTPServer:
    return AuditorHTTPServer((host, port), auditor, mock_registry)
