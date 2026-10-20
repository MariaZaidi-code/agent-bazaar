from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.config import Settings
from app.core.cache import Cache, make_key
from app.knowledge.retrieval import TfidfIndex
from app.schemas import ToolSpec


@dataclass
class ProviderResponse:
    status: str = "success"
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    latency_ms: float = 0.0
    cached: bool = False
    source: str = "live"
    warning: str | None = None
    schema_valid: bool = True
    schema_errors: list[str] = field(default_factory=list)


class BaseProvider(ABC):
    def __init__(self, spec: ToolSpec, settings: Settings, cache: Cache) -> None:
        self.spec = spec
        self.settings = settings
        self.cache = cache
        self.fail_next = 0
        self.offline_forced = False

    @property
    def provider_id(self) -> str:
        return self.spec.provider_id

    @property
    def tool_id(self) -> str:
        return self.spec.id

    def force_failure(self, times: int = 1) -> None:
        self.fail_next = max(1, times)

    def clear_failure(self) -> None:
        self.fail_next = 0

    def set_offline(self, value: bool) -> None:
        self.offline_forced = value

    def status(self) -> dict[str, Any]:
        return {
            "provider_id": self.provider_id,
            "tool_id": self.tool_id,
            "mode": "offline" if (self.settings.offline_mode or self.offline_forced) else "live",
            "forced_offline": self.offline_forced,
            "fail_next": self.fail_next,
            "probe_eligible": self.spec.probe_eligible,
            "execution": self.spec.execution,
        }

    async def call(
        self,
        params: dict[str, Any],
        correlation_id: str = "",
    ) -> ProviderResponse:
        started = time.perf_counter()
        if self.fail_next > 0:
            self.fail_next -= 1
            return ProviderResponse(
                status="error",
                error="Injected provider outage for the demonstration.",
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                source="mock",
                schema_valid=False,
            )
        cache_key = make_key(f"provider:{self.provider_id}", params)
        cached = self.cache.get(cache_key)
        if cached is not None:
            data, source = cached
            valid, errors = self.validate_schema(data)
            return ProviderResponse(
                status="success",
                data=data,
                cached=True,
                source=source,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                schema_valid=valid,
                schema_errors=errors,
            )
        forced_offline = self.settings.offline_mode or self.offline_forced
        if forced_offline:
            try:
                data = await self.offline(params)
                valid, errors = self.validate_schema(data)
                self.cache.set(cache_key, data, source="fixture")
                return ProviderResponse(
                    status="success",
                    data=data,
                    cached=False,
                    source="fixture",
                    warning="Offline demo fixture; no live provider was contacted.",
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    schema_valid=valid,
                    schema_errors=errors,
                )
            except Exception as exc:
                return ProviderResponse(
                    status="error",
                    error=f"Offline fixture failed: {exc}",
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    source="fixture",
                    schema_valid=False,
                )
        try:
            data = await self.execute(params)
            valid, errors = self.validate_schema(data)
            if valid:
                self.cache.set(cache_key, data, source="live")
            return ProviderResponse(
                status="success",
                data=data,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                source="live",
                schema_valid=valid,
                schema_errors=errors,
            )
        except Exception as exc:
            try:
                data = await self.offline(params)
                valid, errors = self.validate_schema(data)
                self.cache.set(cache_key, data, source="fixture", ttl_seconds=300)
                return ProviderResponse(
                    status="success",
                    data=data,
                    cached=False,
                    source="fixture",
                    warning=f"Live call failed ({exc}); deterministic fixture used.",
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    schema_valid=valid,
                    schema_errors=errors,
                )
            except Exception as fallback_exc:
                return ProviderResponse(
                    status="error",
                    error=f"Live call failed: {exc}; fixture failed: {fallback_exc}",
                    latency_ms=round((time.perf_counter() - started) * 1000, 2),
                    source="live",
                    schema_valid=False,
                )

    def validate_schema(self, data: dict[str, Any]) -> tuple[bool, list[str]]:
        errors: list[str] = []
        if not isinstance(data, dict):
            return False, ["Provider payload is not a JSON object"]
        for output in self.spec.outputs:
            key = output.name or output.concept[:1].lower() + output.concept[1:]
            if key not in data:
                errors.append(f"missing output field {key}")
                continue
            value = data[key]
            if output.datatype == "array" and not isinstance(value, list):
                errors.append(f"{key} is not an array")
            elif output.datatype == "object" and not isinstance(value, dict):
                errors.append(f"{key} is not an object")
            elif output.datatype == "number" and not isinstance(value, (int, float)):
                errors.append(f"{key} is not numeric")
            if output.datatype == "object" and isinstance(value, dict):
                for field in output.fields:
                    if field not in value:
                        errors.append(f"{key}.{field} is missing")
        return not errors, errors

    async def answer(self, question: str) -> str:
        index = TfidfIndex({self.tool_id: self.spec.search_text})
        score = index.search(question, top_k=1)
        relevance = score[0][1] if score else 0.0
        return (
            f"{self.spec.name} ({self.spec.capability}) is relevant at {relevance:.2f}. "
            f"{self.spec.description}"
        )

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError
