"""Staging registry: tracks discovered providers through their lifecycle.

This module provides the staging registry that manages provider state
transitions (discovered → staged → verified → suspended). It is the
central coordination point for the discovery pipeline and enforces
deduplication rules.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from app.discovery.service import (
    ProviderDefinition,
    ProviderState,
    DiscoveryService,
)

LOGGER = logging.getLogger(__name__)


class StagingRegistry:
    """Registry for discovered and staged providers.

    This registry tracks all providers that have been discovered but not yet
    fully verified. It provides:

    - Provider lookup by tool_id, provider_id, or capability
    - State transition management
    - Deduplication against the existing catalogue
    - Persistence of staging state
    """

    def __init__(
        self,
        staging_dir: Path,
        specs_dir: Path,
        overrides_path: Path | None = None,
    ):
        self.staging_dir = staging_dir
        self.specs_dir = specs_dir
        self.overrides_path = overrides_path
        self._service = DiscoveryService(
            specs_dir=specs_dir,
            staging_dir=staging_dir,
            overrides_path=overrides_path,
        )
        self._providers: dict[str, ProviderDefinition] = {}
        self._by_provider: dict[str, ProviderDefinition] = {}
        self._by_capability: dict[str, list[ProviderDefinition]] = {}
        self._load()

    def _load(self) -> None:
        """Load staged providers from disk."""
        for definition in self._service.load_staged():
            self.register(definition)

    def register(self, definition: ProviderDefinition) -> ProviderDefinition:
        """Register a provider definition in the registry."""
        self._providers[definition.tool_id] = definition
        self._by_provider[definition.provider_id] = definition
        for capability in definition.capabilities:
            self._by_capability.setdefault(capability, []).append(definition)
        return definition

    def get(self, tool_id: str) -> ProviderDefinition | None:
        """Get a provider by tool_id."""
        return self._providers.get(tool_id)

    def by_provider(self, provider_id: str) -> ProviderDefinition | None:
        """Get a provider by provider_id."""
        return self._by_provider.get(provider_id)

    def by_capability(self, capability: str) -> list[ProviderDefinition]:
        """Get all staged providers for a capability."""
        return self._by_capability.get(capability, [])

    def discovered(self) -> list[ProviderDefinition]:
        """Get all discovered (not yet staged) providers."""
        return [p for p in self._providers.values() if p.state == ProviderState.DISCOVERED]

    def staged(self) -> list[ProviderDefinition]:
        """Get all staged providers awaiting verification."""
        return [p for p in self._providers.values() if p.state == ProviderState.STAGED]

    def verified(self) -> list[ProviderDefinition]:
        """Get all verified providers."""
        return [p for p in self._providers.values() if p.state == ProviderState.VERIFIED]

    def suspended(self) -> list[ProviderDefinition]:
        """Get all suspended providers."""
        return [p for p in self._providers.values() if p.state == ProviderState.SUSPENDED]

    def all(self) -> list[ProviderDefinition]:
        """Get all registered providers."""
        return list(self._providers.values())

    def count_by_state(self) -> dict[str, int]:
        """Count providers by state."""
        counts: dict[str, int] = {state.lower(): 0 for state in ProviderState.__dict__ if not state.startswith("_")}
        for provider in self._providers.values():
            state_key = provider.state.lower()
            if state_key in counts:
                counts[state_key] += 1
        return counts

    def stage_all(self) -> list[ProviderDefinition]:
        """Stage all discovered providers."""
        staged = []
        for provider in self.discovered():
            staged_provider = self._service.stage(provider)
            self.register(staged_provider)
            staged.append(staged_provider)
        return staged

    def verify_all(self, checks: list[str] | None = None) -> list[ProviderDefinition]:
        """Verify all staged providers."""
        verified = []
        for provider in self.staged():
            verified_provider = self._service.verify(provider, checks=checks)
            self.register(verified_provider)
            verified.append(verified_provider)
        return verified

    def suspend_all(self, reason: str = "verification failed") -> list[ProviderDefinition]:
        """Suspend all staged providers."""
        suspended = []
        for provider in self.staged():
            suspended_provider = self._service.suspend(provider, reason)
            self.register(suspended_provider)
            suspended.append(suspended_provider)
        return suspended

    def to_catalogue_entries(self, verified_only: bool = True) -> list[dict]:
        """Convert registered providers to catalogue entries.

        This produces the format expected by the existing catalogue and
        ProviderRegistry. Verified providers are included by default;
        set verified_only=False to include all states.
        """
        entries = []
        for provider in self.all():
            if verified_only and provider.state != ProviderState.VERIFIED:
                continue
            spec = provider.to_tool_spec()
            entry = spec.model_dump(mode="json")
            entry["state"] = provider.state
            entry["discovered_at"] = provider.discovered_at
            entry["staged_at"] = provider.staged_at
            entry["verified_at"] = provider.verified_at
            if provider.suspended_reason:
                entry["suspended_reason"] = provider.suspended_reason
            if provider.duplicate_of:
                entry["duplicate_of"] = provider.duplicate_of
            entries.append(entry)
        return entries

    def export_staging_json(self, path: Path) -> None:
        """Export the full staging registry to a JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "counts": self.count_by_state(),
            "providers": [self._service._definition_to_dict(p) for p in self.all()],
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def import_staging_json(self, path: Path) -> int:
        """Import providers from a staging JSON file."""
        if not path.exists():
            return 0
        data = json.loads(path.read_text(encoding="utf-8"))
        providers_data = data.get("providers", [])
        count = 0
        for provider_data in providers_data:
            try:
                definition = self._service._dict_to_definition(provider_data)
                self.register(definition)
                count += 1
            except Exception as exc:
                LOGGER.warning("failed to import provider: %s", exc)
        return count

    def stats(self) -> dict[str, Any]:
        """Return registry statistics."""
        return {
            "total": len(self._providers),
            "by_state": self.count_by_state(),
            "discovered": len(self.discovered()),
            "staged": len(self.staged()),
            "verified": len(self.verified()),
            "suspended": len(self.suspended()),
            "capabilities": list(self._by_capability.keys()),
        }
