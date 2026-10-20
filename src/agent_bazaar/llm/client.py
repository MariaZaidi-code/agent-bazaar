"""Free-tier hosted LLM client with mandatory disk caching.

Supports any OpenAI-compatible chat completions endpoint (Groq, Gemini and
OpenRouter are pre-configured). The ``offline`` provider never calls the network
and replays cached responses only, which is what the demonstration fallback uses.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from pydantic import BaseModel, ValidationError

from agent_bazaar.config import LLMSettings, get_settings
from agent_bazaar.llm.cache import JsonDiskCache

PROVIDERS: dict[str, dict[str, str]] = {
    "groq": {"base_url": "https://api.groq.com/openai/v1", "api_key_env": "GROQ_API_KEY"},
    "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai", "api_key_env": "GEMINI_API_KEY"},
    "openrouter": {"base_url": "https://openrouter.ai/api/v1", "api_key_env": "OPENROUTER_API_KEY"},
}

JSON_INSTRUCTION = (
    "Respond with a single JSON object only. No markdown fences, no commentary. "
    "The JSON must validate against this schema: {schema}"
)


class LLMError(Exception):
    pass


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def extract_json(text: str) -> str:
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    candidate = fenced.group(1) if fenced else text
    match = _JSON_BLOCK.search(candidate)
    if not match:
        raise LLMError(f"no JSON object found in response: {text[:200]!r}")
    return match.group(0)


class LLMClient:
    def __init__(
        self,
        *,
        provider: str | None = None,
        model: str | None = None,
        cache_dir: str | Path | None = None,
        settings: LLMSettings | None = None,
        temperature: float | None = None,
        timeout_s: int | None = None,
        max_retries: int | None = None,
    ):
        settings = settings or get_settings().llm
        self.provider = (provider or settings.provider).lower()
        self.model = model or settings.model_for(self.provider)
        self.temperature = settings.temperature if temperature is None else temperature
        self.timeout_s = timeout_s or settings.timeout_s
        self.max_retries = max_retries if max_retries is not None else settings.max_retries
        self.cache = JsonDiskCache(cache_dir or get_settings().paths.cache_dir / "llm")
        self._stats: dict[str, Any] = {
            "calls": 0,
            "cache_hits": 0,
            "errors": 0,
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "latency_ms_total": 0.0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        stats = dict(self._stats)
        calls = max(1, stats["calls"])
        stats["avg_latency_ms"] = round(stats["latency_ms_total"] / calls, 2)
        return stats

    def _endpoint(self) -> tuple[str, str]:
        if self.provider not in PROVIDERS:
            raise LLMError(f"unknown provider {self.provider!r}; choose from {sorted(PROVIDERS)} or 'offline'")
        config = PROVIDERS[self.provider]
        api_key = os.environ.get(config["api_key_env"], "")
        if not api_key:
            raise LLMError(f"missing API key: set {config['api_key_env']} or use provider 'offline'")
        return config["base_url"].rstrip("/") + "/chat/completions", api_key

    def _cache_key(self, system: str, user: str, schema: str, cache_scope: str) -> str:
        return JsonDiskCache.make_key(cache_scope, self.provider, self.model, system, user, schema)

    def _call_api(self, messages: list[dict[str, str]], *, json_mode: bool) -> dict[str, Any]:
        url, api_key = self._endpoint()
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            started = time.perf_counter()
            try:
                response = requests.post(url, json=payload, headers=headers, timeout=self.timeout_s)
                self._stats["latency_ms_total"] += (time.perf_counter() - started) * 1000
                if response.status_code == 429 or response.status_code >= 500:
                    raise LLMError(f"provider returned {response.status_code}: {response.text[:200]}")
                if response.status_code >= 400:
                    raise LLMError(f"provider rejected the request ({response.status_code}): {response.text[:300]}")
                return response.json()
            except (requests.RequestException, LLMError) as error:
                last_error = error
                self._stats["errors"] += 1
                if attempt < self.max_retries:
                    time.sleep(min(2 ** attempt, 8))
        raise LLMError(f"LLM call failed after {self.max_retries} attempts: {last_error}")

    def complete(
        self,
        system: str,
        user: str,
        *,
        json_mode: bool = False,
        use_cache: bool = True,
        schema_hint: str = "",
        cache_scope: str = "text",
    ) -> str:
        key = self._cache_key(system, user, schema_hint, cache_scope)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached["text"]
        if self.provider == "offline":
            raise LLMError("offline mode: no cached response available for this prompt")
        full_system = system
        if json_mode and schema_hint:
            full_system = system + "\n\n" + JSON_INSTRUCTION.format(schema=schema_hint)
        body = self._call_api(
            [{"role": "system", "content": full_system}, {"role": "user", "content": user}],
            json_mode=json_mode,
        )
        self._stats["calls"] += 1
        usage = body.get("usage") or {}
        self._stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
        self._stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
        text = body["choices"][0]["message"]["content"] or ""
        if use_cache:
            self.cache.set(key, {"text": text, "model": self.model, "provider": self.provider})
        return text

    def complete_text(self, system: str, user: str, *, use_cache: bool = True, temperature: float | None = None) -> str:
        return self.complete(system, user, use_cache=use_cache, cache_scope="text")

    def complete_json(
        self,
        system: str,
        user: str,
        schema: type[BaseModel],
        *,
        use_cache: bool = True,
        temperature: float | None = None,
    ) -> Any:
        schema_hint = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        cache_scope = f"json:{schema.__name__}"
        key = self._cache_key(system, user, schema_hint, cache_scope)
        if use_cache:
            cached = self.cache.get(key)
            if cached is not None and cached.get("parsed") is not None:
                self._stats["cache_hits"] += 1
                return schema.model_validate(cached["parsed"])
        raw = self.complete(
            system,
            user,
            json_mode=True,
            use_cache=False,
            schema_hint=schema_hint,
            cache_scope=cache_scope,
        )
        parsed = self._parse_validate(raw, schema)
        if parsed is None:
            repair_user = (
                f"{user}\n\nYour previous reply was invalid JSON or did not match the schema. "
                f"Reply again with one valid JSON object only.\nPrevious reply:\n{raw[:1500]}"
            )
            raw = self.complete(
                system,
                repair_user,
                json_mode=True,
                use_cache=False,
                schema_hint=schema_hint,
                cache_scope=cache_scope,
            )
            parsed = self._parse_validate(raw, schema)
        if parsed is None:
            raise LLMError(f"could not obtain valid JSON for {schema.__name__}")
        if use_cache:
            self.cache.set(key, {"text": raw, "parsed": parsed.model_dump(mode="json"), "model": self.model})
        return parsed

    @staticmethod
    def _parse_validate(raw: str, schema: type[BaseModel]) -> Any | None:
        try:
            data = json.loads(extract_json(raw))
        except (json.JSONDecodeError, LLMError):
            return None
        try:
            return schema.model_validate(data)
        except ValidationError:
            return None


def build_llm_client(**kwargs: Any) -> LLMClient:
    settings = get_settings()
    return LLMClient(settings=settings.llm, cache_dir=settings.paths.cache_dir / "llm", **kwargs)
