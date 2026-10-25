from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .config import Settings
from .utils import atomic_write_json, read_json

JSON_BLOCK = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


class LLMClient(Protocol):
    def complete_json(self, prompt: str) -> dict[str, Any]:
        ...

    def complete_text(self, prompt: str) -> str:
        ...


@dataclass
class LLMUsage:
    calls: int = 0
    cache_hits: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0

    def to_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "cache_hits": self.cache_hits,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
        }


class CachedLLM:
    def __init__(self, backend: LLMClient, cache_dir: Path | str = ".cache/llm", model: str = "unknown") -> None:
        self.backend = backend
        self.cache_dir = Path(cache_dir)
        self.model = model
        self.usage = LLMUsage()

    def _key(self, prompt: str, mode: str) -> str:
        digest = hashlib.sha256(f"{self.model}|{mode}|{prompt}".encode()).hexdigest()
        return digest

    def _path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _cached(self, path: Path) -> Any | None:
        if not path.exists():
            return None
        try:
            return read_json(path)["response"]
        except (OSError, ValueError, KeyError):
            return None

    def _store(self, path: Path, response: Any, usage: dict[str, int] | None = None) -> None:
        atomic_write_json(path, {"response": response, "usage": usage or {}, "model": self.model})

    def complete_text(self, prompt: str) -> str:
        return self._complete(prompt, mode="text")

    def complete_json(self, prompt: str) -> dict[str, Any]:
        response = self._complete(prompt, mode="json")
        if isinstance(response, dict):
            return response
        if isinstance(response, str):
            return extract_json(response)
        raise ValueError("LLM JSON response was not an object")

    def _complete(self, prompt: str, mode: str) -> Any:
        path = self._path(self._key(prompt, mode))
        cached = self._cached(path)
        if cached is not None:
            self.usage.cache_hits += 1
            return cached
        self.usage.calls += 1
        if mode == "json":
            result = self.backend.complete_json(prompt)
        else:
            result = self.backend.complete_text(prompt)
        self._store(path, result)
        return result


@dataclass
class OpenAICompatibleLLM:
    base_url: str
    api_key: str
    model: str
    timeout: float = 60.0
    temperature: float = 0.0
    usage: dict[str, int] = field(default_factory=dict)

    def _post(self, messages: list[dict[str, str]], json_mode: bool) -> str:
        url = self.base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        request = urllib.request.Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "User-Agent": "agent-bazaar-auditor/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"LLM request failed with HTTP {error.code}: {detail}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise RuntimeError(f"LLM request failed: {error}") from error
        usage = payload.get("usage") or {}
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            self.usage[key] = self.usage.get(key, 0) + int(usage.get(key, 0))
        try:
            return str(payload["choices"][0]["message"]["content"])
        except (KeyError, IndexError, TypeError) as error:
            raise RuntimeError("LLM response did not contain a message") from error

    def complete_text(self, prompt: str) -> str:
        return self._post([{"role": "user", "content": prompt}], json_mode=False)

    def complete_json(self, prompt: str) -> dict[str, Any]:
        response = self._post(
            [
                {"role": "system", "content": "Return only a valid JSON object. Do not add commentary."},
                {"role": "user", "content": prompt},
            ],
            json_mode=True,
        )
        return extract_json(response)


def extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    match = JSON_BLOCK.search(text)
    if match:
        text = match.group(1)
    try:
        payload = json.loads(text)
    except ValueError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("No JSON object found in LLM response") from None
        payload = json.loads(text[start : end + 1])
    if not isinstance(payload, dict):
        raise ValueError("LLM JSON response was not an object")
    return payload


def build_llm(settings: Settings | None = None) -> CachedLLM | None:
    settings = settings or Settings.from_env()
    if not settings.llm_base_url or not settings.llm_model:
        return None
    backend = OpenAICompatibleLLM(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
        timeout=settings.request_timeout_seconds * 4.0,
    )
    return CachedLLM(backend, settings.cache_dir / "llm", settings.llm_model)
