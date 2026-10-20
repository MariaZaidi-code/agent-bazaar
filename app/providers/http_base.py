from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.providers.base import BaseProvider


class HTTPProvider(BaseProvider):
    user_agent = "AgentBazaar/0.1 (university project; contact: team@agentbazaar.local)"
    min_interval_seconds = 0.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._throttle_lock = asyncio.Lock()
        self._last_request = 0.0

    async def _throttle(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        async with self._throttle_lock:
            elapsed = time.monotonic() - self._last_request
            wait = self.min_interval_seconds - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        await self._throttle()
        merged_headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        if headers:
            merged_headers.update(headers)
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, params=params, headers=merged_headers)
            response.raise_for_status()
            return response.json()

    async def get_text(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> str:
        await self._throttle()
        merged_headers = {"User-Agent": self.user_agent}
        if headers:
            merged_headers.update(headers)
        async with httpx.AsyncClient(
            timeout=self.settings.request_timeout_seconds,
            follow_redirects=True,
        ) as client:
            response = await client.get(url, params=params, headers=merged_headers)
            response.raise_for_status()
            return response.text
