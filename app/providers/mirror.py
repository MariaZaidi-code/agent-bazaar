from __future__ import annotations

from typing import Any

from app.providers.base import BaseProvider, ProviderResponse
from app.schemas import ClaimLabel, ClaimSpec, ToolSpec


def make_mirror_spec(primary: ToolSpec) -> ToolSpec:
    claims = [
        ClaimSpec(
            text=claim.text,
            label=ClaimLabel.unsupported,
            evidence="Backup mirror; not independently verified.",
        )
        for claim in primary.claims
    ]
    return primary.model_copy(
        update={
            "id": f"{primary.id}-backup",
            "provider_id": f"{primary.provider_id}-backup",
            "name": f"{primary.name} (Backup Mirror)",
            "description": (
                "Standby backup mirror used to test circuit-breaker substitution. "
                f"Mirrors {primary.name}. {primary.description}"
            ),
            "claims": claims,
            "tags": [*primary.tags, "backup"],
            "execution": "mock",
            "probe_eligible": False,
        }
    )


class MirrorProvider(BaseProvider):
    def __init__(self, primary: BaseProvider, mirror_spec: ToolSpec) -> None:
        super().__init__(mirror_spec, primary.settings, primary.cache)
        self.primary = primary

    def status(self) -> dict[str, Any]:
        payload = super().status()
        payload["mirror_of"] = self.primary.tool_id
        return payload

    async def execute(self, params: dict[str, Any]) -> dict[str, Any]:
        if self.settings.offline_mode or self.primary.offline_forced:
            return await self.primary.offline(params)
        try:
            return await self.primary.execute(params)
        except Exception:
            return await self.primary.offline(params)

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        return await self.primary.offline(params)

    async def call(
        self, params: dict[str, Any], correlation_id: str = ""
    ) -> ProviderResponse:
        return await super().call(params, correlation_id=correlation_id)
