from __future__ import annotations

from typing import Any

from app.providers.http_base import HTTPProvider

DISCOVERED_CONFIG: dict[str, dict[str, Any]] = {}


class GenericHttpProvider(HTTPProvider):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        cfg = DISCOVERED_CONFIG.get(self.spec.id, {})
        self.base_url = str(cfg.get("base_url", ""))
        self.path = str(cfg.get("path", ""))
        self.default_params = cfg.get("params", {})

    def _config(self) -> dict[str, Any]:
        cfg = DISCOVERED_CONFIG.get(self.spec.id, {})
        if cfg:
            self.base_url = str(cfg.get("base_url", self.base_url))
            self.path = str(cfg.get("path", self.path))
            self.default_params = cfg.get("params", self.default_params)
        return cfg

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        self._config()
        url = self.base_url.rstrip("/") + self.path
        query: dict[str, Any] = {}
        if isinstance(self.default_params, dict):
            query.update(self.default_params)
        if isinstance(params, dict):
            query.update(params)
        payload = await self.get_json(url, params=query)
        if isinstance(payload, dict):
            return payload
        return {"result": payload}

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return {"result": "offline fixture"}
