from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings
from app.core.cache import Cache, make_key


@dataclass
class LLMResult:
    text: str = ""
    tokens: int = 0
    cached: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        return bool(self.text) and self.error is None


class LLMClient:
    PRESETS = {
        "openrouter": "https://openrouter.ai/api/v1",
        "groq": "https://api.groq.com/openai/v1",
        "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    }

    def __init__(self, settings: Settings, cache: Cache) -> None:
        self.settings = settings
        self.cache = cache
        self.provider = settings.llm_provider.strip().lower()
        base_url = settings.llm_base_url.rstrip("/")
        if self.provider in self.PRESETS and base_url == self.PRESETS["openrouter"]:
            base_url = self.PRESETS[self.provider]
        self.base_url = base_url

    @property
    def enabled(self) -> bool:
        return self.provider in self.PRESETS and bool(self.settings.llm_api_key)

    async def complete(
        self,
        prompt: str,
        system: str | None = None,
        json_mode: bool = False,
        temperature: float = 0.0,
        max_tokens: int = 900,
    ) -> LLMResult:
        if not self.enabled:
            return LLMResult(error="LLM disabled; deterministic fallback used")
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        key = make_key(
            "llm",
            {
                "provider": self.provider,
                "model": self.settings.llm_model,
                "messages": messages,
                "json_mode": json_mode,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        cached = self.cache.get(key)
        if cached is not None:
            payload, _ = cached
            return LLMResult(
                text=str(payload.get("text", "")),
                tokens=int(payload.get("tokens", 0)),
                cached=True,
            )
        request: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            request["response_format"] = {"type": "json_object"}
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
            "X-Title": "Agent Bazaar",
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.llm_timeout_seconds
            ) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=request,
                )
                response.raise_for_status()
                data = response.json()
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage") or {}
            tokens = int(usage.get("prompt_tokens", 0)) + int(
                usage.get("completion_tokens", 0)
            )
            self.cache.set(key, {"text": text, "tokens": tokens}, source="llm")
            return LLMResult(text=text, tokens=tokens)
        except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
            return LLMResult(error=f"LLM request failed: {exc}")

    @staticmethod
    def parse_json_object(text: str) -> dict[str, Any] | None:
        if not text:
            return None
        candidate = text.strip()
        fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", candidate, re.S)
        if fenced:
            candidate = fenced.group(1)
        else:
            start = candidate.find("{")
            end = candidate.rfind("}")
            if start >= 0 and end > start:
                candidate = candidate[start : end + 1]
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None


async def gather_with_timeout(coros: list[Any], timeout: float) -> list[Any]:
    if not coros:
        return []
    return await asyncio.wait_for(asyncio.gather(*coros), timeout=timeout)
