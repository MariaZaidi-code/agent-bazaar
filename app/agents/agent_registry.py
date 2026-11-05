from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass
class AgentSpec:
    name: str
    capability: str
    description: str
    handler: Callable[[dict[str, Any]], dict[str, Any]]


@dataclass
class AgentHealth:
    calls: int = 0
    errors: int = 0
    total_latency_ms: float = 0.0

    @property
    def health_score(self) -> float:
        if self.calls == 0:
            return 100.0
        uptime = (self.calls - self.errors) / self.calls
        latency_penalty = 1.0 if self.total_latency_ms / self.calls < 1000 else 0.8
        return round(uptime * 100.0 * latency_penalty, 2)


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, AgentSpec] = {}
        self._health: dict[str, AgentHealth] = {}

    def register(self, spec: AgentSpec) -> None:
        self._agents[spec.name] = spec
        self._health.setdefault(spec.name, AgentHealth())

    def agents(self) -> list[dict[str, Any]]:
        return [
            {
                "name": spec.name,
                "capability": spec.capability,
                "description": spec.description,
                "health": {
                    "calls": self._health[spec.name].calls,
                    "errors": self._health[spec.name].errors,
                    "health_score": self._health[spec.name].health_score,
                },
            }
            for spec in self._agents.values()
        ]

    def run(self, name: str, payload: dict[str, Any]) -> dict[str, Any]:
        spec = self._agents.get(name)
        if spec is None:
            raise ValueError(f"Unknown agent: {name}")
        health = self._health[name]
        started = time.perf_counter()
        try:
            result = spec.handler(payload)
            status = "success"
            error = None
        except Exception as exc:  # pragma: no cover - defensive boundary
            result = None
            status = "error"
            error = str(exc)
        health.calls += 1
        if status == "error":
            health.errors += 1
        health.total_latency_ms += (time.perf_counter() - started) * 1000.0
        if status == "error":
            raise RuntimeError(error or "agent failed")
        return {"agent": name, "status": status, "result": result}

    def health(self, name: str) -> dict[str, Any]:
        health = self._health.get(name)
        if health is None:
            raise ValueError(f"Unknown agent: {name}")
        return {"calls": health.calls, "errors": health.errors, "health_score": health.health_score}
