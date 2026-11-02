"""Deterministic offline fixture system for GenericProvider.

Fixtures are stored per provider and endpoint, and selected based on request
characteristics. The system never fabricates successful responses: when no
fixture matches, execution fails with an explicit error.

Fixture types:
- success: valid response matching the endpoint schema
- auth_failure: 401/403 response
- rate_limit: 429 response
- timeout: simulated timeout
- schema_violation: response that fails schema validation
- error: 5xx response
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)

FIXTURE_TYPES = frozenset(
    {
        "success",
        "auth_failure",
        "rate_limit",
        "timeout",
        "schema_violation",
        "error",
    }
)


@dataclass
class Fixture:
    """A single fixture response for an endpoint."""

    tool_id: str
    endpoint_path: str
    method: str
    fixture_type: str = "success"
    status_code: int = 200
    headers: dict[str, str] = field(default_factory=dict)
    body: Any = field(default_factory=dict)
    error: str | None = None
    delay_seconds: float = 0.0
    content_type: str = "application/json"
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "endpoint_path": self.endpoint_path,
            "method": self.method,
            "fixture_type": self.fixture_type,
            "status_code": self.status_code,
            "headers": self.headers,
            "body": self.body,
            "error": self.error,
            "delay_seconds": self.delay_seconds,
            "content_type": self.content_type,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Fixture":
        return cls(
            tool_id=data["tool_id"],
            endpoint_path=data["endpoint_path"],
            method=data["method"],
            fixture_type=data.get("fixture_type", "success"),
            status_code=data.get("status_code", 200),
            headers=data.get("headers", {}),
            body=data.get("body", {}),
            error=data.get("error"),
            delay_seconds=data.get("delay_seconds", 0.0),
            content_type=data.get("content_type", "application/json"),
            created_at=data.get("created_at", time.time()),
        )


class FixtureStore:
    """Deterministic fixture storage and retrieval.

    Fixtures are stored as JSON files under a base directory, organized by
    tool_id. Selection is deterministic: given the same tool_id, endpoint,
    method, and params, the same fixture is always returned.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _fixture_path(self, tool_id: str) -> Path:
        safe_id = hashlib.sha256(tool_id.encode()).hexdigest()[:16]
        return self.base_dir / f"{safe_id}.json"

    def save(self, fixture: Fixture) -> Path:
        """Persist a fixture to disk."""
        path = self._fixture_path(fixture.tool_id)
        fixtures = self._load_file(path)

        # Replace existing fixture for same endpoint+method+type
        fixtures = [
            f
            for f in fixtures
            if not (
                f.get("endpoint_path") == fixture.endpoint_path
                and f.get("method") == fixture.method
                and f.get("fixture_type") == fixture.fixture_type
            )
        ]
        fixtures.append(fixture.to_dict())

        path.write_text(json.dumps(fixtures, indent=2), encoding="utf-8")
        return path

    def _load_file(self, path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def get(
        self,
        tool_id: str,
        endpoint_path: str,
        method: str,
        params: dict[str, Any] | None = None,
        preferred_type: str = "success",
    ) -> Fixture | None:
        """Retrieve a fixture deterministically.

        Selection order:
        1. Exact match for preferred_type
        2. Any success fixture
        3. Any fixture (fallback, returns error fixture if none succeed)
        """
        path = self._fixture_path(tool_id)
        fixtures_data = self._load_file(path)

        if not fixtures_data:
            return None

        fixtures = [Fixture.from_dict(f) for f in fixtures_data]
        matching = [f for f in fixtures if f.endpoint_path == endpoint_path and f.method.upper() == method.upper()]

        if not matching:
            return None

        # Prefer requested type
        for f in matching:
            if f.fixture_type == preferred_type:
                return f

        # Fall back to success
        for f in matching:
            if f.fixture_type == "success":
                return f

        # Return first available
        return matching[0]

    def generate_success_fixture(
        self,
        tool_id: str,
        endpoint_path: str,
        method: str,
        response_fields: list[dict[str, Any]] | None = None,
    ) -> Fixture:
        """Generate a deterministic success fixture from endpoint response fields.

        Values are derived from the field names and types using a deterministic
        hash, so the same endpoint always produces the same fixture.
        """
        body: dict[str, Any] = {}
        response_fields = response_fields or []

        for field_spec in response_fields:
            name = field_spec.get("name", "")
            ftype = field_spec.get("type", "string")
            if not name:
                continue

            seed = hashlib.sha256(f"{tool_id}:{endpoint_path}:{name}".encode()).digest()

            if ftype == "string":
                body[name] = f"fixture_{name}_{seed[0]:02x}"
            elif ftype in ("integer", "int"):
                body[name] = seed[0]
            elif ftype in ("number", "float"):
                body[name] = round(seed[0] / 255.0 * 100.0, 2)
            elif ftype == "boolean":
                body[name] = seed[0] % 2 == 0
            elif ftype == "array":
                body[name] = [f"fixture_item_{i}" for i in range(2)]
            elif ftype == "object":
                body[name] = {"fixture_key": f"fixture_value_{seed[0]:02x}"}
            else:
                body[name] = f"fixture_{name}"

        return Fixture(
            tool_id=tool_id,
            endpoint_path=endpoint_path,
            method=method.upper(),
            fixture_type="success",
            status_code=200,
            body=body,
        )

    def generate_error_fixture(
        self,
        tool_id: str,
        endpoint_path: str,
        method: str,
        fixture_type: str = "error",
    ) -> Fixture:
        """Generate a deterministic error fixture."""
        if fixture_type == "auth_failure":
            return Fixture(
                tool_id=tool_id,
                endpoint_path=endpoint_path,
                method=method.upper(),
                fixture_type="auth_failure",
                status_code=401,
                body={"error": "Unauthorized", "message": "Invalid API key"},
            )
        elif fixture_type == "rate_limit":
            return Fixture(
                tool_id=tool_id,
                endpoint_path=endpoint_path,
                method=method.upper(),
                fixture_type="rate_limit",
                status_code=429,
                body={"error": "Rate limit exceeded", "retry_after": 60},
            )
        elif fixture_type == "timeout":
            return Fixture(
                tool_id=tool_id,
                endpoint_path=endpoint_path,
                method=method.upper(),
                fixture_type="timeout",
                status_code=0,
                body={},
                error="Request timed out",
                delay_seconds=30.0,
            )
        elif fixture_type == "schema_violation":
            return Fixture(
                tool_id=tool_id,
                endpoint_path=endpoint_path,
                method=method.upper(),
                fixture_type="schema_violation",
                status_code=200,
                body={"unexpected_field": "value", "wrong_type": 12345},
            )
        else:
            return Fixture(
                tool_id=tool_id,
                endpoint_path=endpoint_path,
                method=method.upper(),
                fixture_type="error",
                status_code=500,
                body={"error": "Internal server error"},
            )

    def list_fixtures(self, tool_id: str) -> list[Fixture]:
        """List all fixtures for a tool."""
        path = self._fixture_path(tool_id)
        fixtures_data = self._load_file(path)
        return [Fixture.from_dict(f) for f in fixtures_data]

    def clear(self, tool_id: str) -> int:
        """Remove all fixtures for a tool. Returns count removed."""
        path = self._fixture_path(tool_id)
        fixtures = self._load_file(path)
        if path.exists():
            path.unlink()
        return len(fixtures)
