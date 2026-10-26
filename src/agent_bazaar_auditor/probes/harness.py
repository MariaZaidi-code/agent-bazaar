from __future__ import annotations

import copy
import json
import time
import xml.etree.ElementTree as ElementTree
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..enums import ProbeSource
from ..messages import _json_value
from ..utils import canonical_json, utc_now
from .cache import ProbeCache
from .definitions import ProbeDefinition, build_probe_definitions
from .http import HttpTransport, RateLimiter, TransportError
from .models import ProbeResult, validate_payload

LIST_TAGS = {"entry", "link", "author", "category", "item"}


@dataclass
class ParsedBody:
    value: Any
    raw_text: str
    error: str = ""


def xml_to_value(element: ElementTree.Element) -> Any:
    tag = element.tag.split("}")[-1]
    children = list(element)
    if not children:
        return (element.text or "").strip()
    grouped: dict[str, list[Any]] = {}
    for child in children:
        child_tag = child.tag.split("}")[-1]
        grouped.setdefault(child_tag, []).append(xml_to_value(child))
    result: dict[str, Any] = {}
    for child_tag, values in grouped.items():
        if child_tag in LIST_TAGS or len(values) > 1:
            result[child_tag] = values
        else:
            result[child_tag] = values[0]
    result.setdefault("tag", tag)
    return result


def parse_body(body: str) -> ParsedBody:
    text = body.strip()
    if not text:
        return ParsedBody(None, body, "Empty response body")
    if text.startswith("{") or text.startswith("["):
        try:
            return ParsedBody(json.loads(text), body)
        except ValueError as error:
            return ParsedBody(None, body, f"Invalid JSON: {error}")
    if text.startswith("<"):
        try:
            root = ElementTree.fromstring(text)
            root_tag = root.tag.split("}")[-1]
            return ParsedBody({root_tag: xml_to_value(root)}, body)
        except ElementTree.ParseError as error:
            return ParsedBody(None, body, f"Invalid XML: {error}")
    return ParsedBody(text, body)


class ProbeHarness:
    def __init__(
        self,
        definitions: dict[str, ProbeDefinition] | None = None,
        live: bool = False,
        cache_dir: Path | str = ".cache/probes",
        transport: HttpTransport | None = None,
        providers: dict[str, Any] | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        self.definitions = definitions or build_probe_definitions()
        self.live = live
        self.cache = ProbeCache(cache_dir)
        self.transport = transport or HttpTransport()
        self.providers = providers or {}
        self.rate_limiter = rate_limiter or RateLimiter()
        self.last_results: dict[str, ProbeResult] = {}

    def get_definition(self, tool_id: str) -> ProbeDefinition:
        try:
            return self.definitions[tool_id]
        except KeyError as error:
            raise KeyError(f"No probe definition for tool {tool_id}") from error

    def set_provider(self, tool_id: str, provider: Any) -> None:
        self.providers[tool_id] = provider

    def remove_provider(self, tool_id: str) -> None:
        self.providers.pop(tool_id, None)

    def probe(self, tool_id: str, force_live: bool = False) -> ProbeResult:
        definition = self.get_definition(tool_id)
        provider = self.providers.get(tool_id)
        if provider is not None:
            response = provider.call(definition.safe_input or definition.params)
            status_code = int(getattr(response, "status_code", 0))
            payload = getattr(response, "payload", None)
            error = getattr(response, "error", "")
            raw_text = getattr(response, "raw_text", "") or canonical_json(_json_value(payload))
            source = getattr(response, "source", ProbeSource.MOCK)
            if isinstance(source, str):
                source = ProbeSource(source)
            result = ProbeResult(
                tool_id=tool_id,
                ok=status_code >= 200 and status_code < 300 and not error,
                status_code=status_code,
                payload=payload,
                source=source,
                raw_text=raw_text,
                latency_ms=float(getattr(response, "latency_ms", 0.0)),
                timestamp=getattr(response, "timestamp", utc_now()),
                error=error,
                url=getattr(response, "url", definition.endpoint),
                metadata={"provider": provider.__class__.__name__, "definition": definition.id},
            )
            self.last_results[tool_id] = result
            return result
        if not (self.live or force_live):
            payload = copy.deepcopy(definition.fixture)
            raw_text = json.dumps(payload, ensure_ascii=False)
            result = ProbeResult(
                tool_id=tool_id,
                ok=definition.fixture_status >= 200 and definition.fixture_status < 300,
                status_code=definition.fixture_status,
                payload=payload,
                source=ProbeSource.FIXTURE,
                raw_text=raw_text,
                latency_ms=0.0,
                url=definition.endpoint,
                metadata={"definition": definition.id, "fixture": True},
            )
            self.last_results[tool_id] = result
            return result
        cached = None if force_live else self.cache.get(tool_id, definition.cache_ttl_seconds)
        if cached is not None:
            result = ProbeResult(
                tool_id=tool_id,
                ok=200 <= int(cached.get("status_code", 0)) < 300,
                status_code=int(cached.get("status_code", 0)),
                payload=cached.get("payload"),
                source=ProbeSource.CACHE,
                raw_text=cached.get("raw_text", ""),
                latency_ms=0.0,
                url=cached.get("url", definition.endpoint),
                cached=True,
                metadata={"definition": definition.id, "cached_at": cached.get("cached_at")},
            )
            self.last_results[tool_id] = result
            return result
        self.rate_limiter.wait(tool_id, definition.min_interval_seconds)
        started = time.monotonic()
        try:
            response = self.transport.get(definition.endpoint, definition.params, definition.headers)
        except TransportError as error:
            result = ProbeResult(
                tool_id=tool_id,
                ok=False,
                status_code=0,
                payload=None,
                source=ProbeSource.LIVE,
                latency_ms=(time.monotonic() - started) * 1000.0,
                error=str(error),
                url=definition.endpoint,
                metadata={"definition": definition.id},
            )
            self.last_results[tool_id] = result
            return result
        parsed = parse_body(response.body)
        result = ProbeResult(
            tool_id=tool_id,
            ok=200 <= response.status_code < 300 and not parsed.error,
            status_code=response.status_code,
            payload=parsed.value,
            source=ProbeSource.LIVE,
            raw_text=response.body,
            latency_ms=response.elapsed_ms,
            error=parsed.error,
            url=response.url,
            metadata={"definition": definition.id, "response_headers": response.headers},
        )
        if result.ok:
            self.cache.set(tool_id, parsed.value, response.status_code, response.url, response.body)
        self.last_results[tool_id] = result
        return result

    def probe_all(self, tool_ids: list[str] | None = None, force_live: bool = False) -> dict[str, ProbeResult]:
        targets = tool_ids or list(self.definitions.keys())
        return {tool_id: self.probe(tool_id, force_live=force_live) for tool_id in targets}

    def validate(self, tool_id: str, result: ProbeResult | None = None):
        definition = self.get_definition(tool_id)
        probe = result or self.last_results.get(tool_id) or self.probe(tool_id)
        return validate_payload(definition, probe.payload)
