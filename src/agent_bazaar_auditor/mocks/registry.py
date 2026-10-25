from __future__ import annotations

from pathlib import Path
from typing import Any

from ..enums import MockBehavior
from ..probes.definitions import ProbeDefinition, build_probe_definitions
from ..probes.harness import ProbeHarness
from ..tools import ToolSpec, build_catalog
from ..utils import read_jsonl
from .provider import MockProvider


class MockRegistry:
    def __init__(
        self,
        harness: ProbeHarness,
        catalog: dict[str, ToolSpec] | None = None,
        definitions: dict[str, ProbeDefinition] | None = None,
        log_path: Path | str | None = None,
    ) -> None:
        self.harness = harness
        self.catalog = catalog or build_catalog()
        self.definitions = definitions or build_probe_definitions()
        self.log_path = Path(log_path) if log_path else None
        self.providers: dict[str, MockProvider] = {}

    def create(
        self,
        tool_id: str,
        behavior: MockBehavior | str = MockBehavior.NORMAL,
        options: dict[str, Any] | None = None,
        seed: int = 7,
    ) -> MockProvider:
        if tool_id not in self.definitions:
            raise KeyError(f"No probe definition for tool {tool_id}")
        tool = self.catalog.get(tool_id)
        provider = MockProvider(
            tool_id=tool_id,
            definition=self.definitions[tool_id],
            behavior=behavior,
            options=options,
            seed=seed,
            log_path=self.log_path,
            documentation=tool.documentation if tool else [],
        )
        self.providers[tool_id] = provider
        self.harness.set_provider(tool_id, provider)
        return provider

    def get(self, tool_id: str) -> MockProvider:
        try:
            return self.providers[tool_id]
        except KeyError as error:
            raise KeyError(f"Mock provider for {tool_id} is not registered") from error

    def control(self, tool_id: str, behavior: MockBehavior | str, **options: Any) -> MockProvider:
        provider = self.providers.get(tool_id)
        if provider is None:
            provider = self.create(tool_id, behavior=behavior, options=options)
        else:
            provider.configure(behavior, **options)
        return provider

    def remove(self, tool_id: str) -> None:
        self.providers.pop(tool_id, None)
        self.harness.remove_provider(tool_id)

    def reset_all(self) -> None:
        for provider in self.providers.values():
            provider.reset()

    def ground_truth(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for provider in self.providers.values():
            records.extend(provider.events)
        if self.log_path is not None and self.log_path.exists():
            records.extend(read_jsonl(self.log_path))
        return records

    def states(self) -> dict[str, dict[str, Any]]:
        return {tool_id: provider.state() for tool_id, provider in self.providers.items()}
