"""End-to-end discovery-to-execution pipeline.

Orchestrates the complete lifecycle:
1. Discover an API
2. Fetch and parse its specification
3. Extract endpoints and capabilities
4. Map capabilities through Mapper
5. Validate mappings (confidence threshold)
6. Verify the provider through Auditor
7. Store verification evidence
8. Register the verified provider
9. Execute it (live or deterministic offline fixtures)
10. Retrieve it through GraphRAG
11. Compose it through ClientAgent
12. Persist all state across restarts

This module is the single entry point that ties the discovery,
mapper, auditor, graph, retriever, and provider registry together.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.discovery.service import (
    DiscoveryService,
    ProviderDefinition,
    ProviderState,
    map_provider_to_ontology,
    verify_provider_with_auditor,
)
from app.discovery.staging import StagingRegistry

LOGGER = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Result of running a provider through the full pipeline."""

    tool_id: str
    stage: str = ""
    discovered: bool = False
    mapped: bool = False
    verified: bool = False
    registered: bool = False
    retrieved: bool = False
    persisted: bool = False
    errors: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    mapping_result: dict[str, Any] = field(default_factory=dict)
    verification_result: dict[str, Any] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return self.discovered and self.verified and not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "stage": self.stage,
            "discovered": self.discovered,
            "mapped": self.mapped,
            "verified": self.verified,
            "registered": self.registered,
            "retrieved": self.retrieved,
            "persisted": self.persisted,
            "success": self.success,
            "errors": self.errors,
            "notes": self.notes,
            "mapping_result": self.mapping_result,
            "verification_result": self.verification_result,
            "duration_ms": self.duration_ms,
        }


class DiscoveryPipeline:
    """Orchestrates the full discovery-to-execution lifecycle.

    Wires together:
    - DiscoveryService (fetch/parse/dedup)
    - Mapper (concept mapping)
    - Auditor (verification)
    - Knowledge graph (persistence)
    - GraphRAG retriever (searchability)
    - StagingRegistry (lifecycle)
    - ProviderRegistry (execution)
    """

    def __init__(
        self,
        staging: StagingRegistry,
        settings: Any,
        mapper: Any = None,
        store: Any = None,
        retriever: Any = None,
        auditor: Any = None,
        provider_registry: Any = None,
        confidence_threshold: float = 0.5,
    ):
        self.staging = staging
        self.settings = settings
        self.mapper = mapper
        self.store = store
        self.retriever = retriever
        self.auditor = auditor
        self.provider_registry = provider_registry
        self.confidence_threshold = confidence_threshold
        self._history: list[dict[str, Any]] = []

    async def run_full_pipeline(
        self,
        content: bytes,
        source: str = "",
        existing_tools: list[dict] | None = None,
        verify_force: bool = False,
    ) -> PipelineResult:
        """Run a specification through the complete pipeline.

        Steps: discover -> map -> verify -> register -> persist.
        """
        started = time.perf_counter()
        result = PipelineResult(tool_id="")

        # Step 1: Discover
        result.stage = "discover"
        try:
            definition = self.staging._service.discover(
                content,
                source=source,
                existing_tools=existing_tools or [],
            )
            if definition is None:
                result.errors.append("Discovery failed: could not parse specification")
                return result
            result.tool_id = definition.tool_id
            result.discovered = True
            result.notes.append(f"Discovered {definition.name}")
        except Exception as e:
            result.errors.append(f"Discovery error: {e}")
            return result

        # Step 2: Stage
        result.stage = "stage"
        try:
            definition = self.staging._service.stage(definition)
            self.staging.register(definition)
            result.notes.append("Staged for processing")
        except Exception as e:
            result.errors.append(f"Staging error: {e}")
            return result

        # Step 3: Map capabilities
        result.stage = "map"
        try:
            result.mapping_result = await map_provider_to_ontology(
                definition,
                mapper=self.mapper,
                store=self.store,
                retriever=self.retriever,
                confidence_threshold=self.confidence_threshold,
            )
            result.mapped = result.mapping_result.get("mapped", False)
            result.persisted = result.mapping_result.get("persisted", False)
            result.retrieved = result.mapping_result.get("retriever_rebuilt", False)
            result.notes.extend(result.mapping_result.get("notes", []))
            if result.mapping_result.get("errors"):
                result.notes.extend(f"Mapping warning: {e}" for e in result.mapping_result["errors"])
        except Exception as e:
            result.errors.append(f"Mapping error: {e}")

        # Step 4: Verify
        result.stage = "verify"
        try:
            result.verification_result = await verify_provider_with_auditor(
                definition,
                auditor=self.auditor,
                settings=self.settings,
            )
            result.verified = result.verification_result.get("verified", False)
            result.notes.extend(result.verification_result.get("notes", []))

            if result.verified:
                definition = self.staging._service.verify(
                    definition,
                    checks=result.verification_result.get("notes", []),
                )
                self.staging.register(definition)
            else:
                definition = self.staging._service.suspend(
                    definition,
                    reason="; ".join(result.verification_result.get("errors", ["verification failed"])),
                )
                self.staging.register(definition)
                result.notes.append("Provider suspended: verification failed")
        except Exception as e:
            result.errors.append(f"Verification error: {e}")

        # Step 5: Register executable provider
        result.stage = "register"
        if result.verified and self.provider_registry is not None:
            try:
                if self.provider_registry.get(definition.tool_id) is None:
                    from app.discovery.runtime import GenericProvider

                    provider = GenericProvider(
                        definition,
                        self.settings,
                        getattr(self.provider_registry, "cache", None),
                    )
                    self.provider_registry.register(provider)
                    result.registered = True
                    result.notes.append("Registered as executable provider")
            except Exception as e:
                result.errors.append(f"Registration error: {e}")

        # Step 6: Record in history
        result.stage = "complete"
        result.duration_ms = round((time.perf_counter() - started) * 1000, 2)
        self._history.append(result.to_dict())

        return result

    async def run_mapping_only(
        self,
        definition: ProviderDefinition,
    ) -> dict[str, Any]:
        """Run only the mapping step for an existing definition."""
        return await map_provider_to_ontology(
            definition,
            mapper=self.mapper,
            store=self.store,
            retriever=self.retriever,
            confidence_threshold=self.confidence_threshold,
        )

    async def run_verification_only(
        self,
        definition: ProviderDefinition,
    ) -> dict[str, Any]:
        """Run only the verification step for an existing definition."""
        return await verify_provider_with_auditor(
            definition,
            auditor=self.auditor,
            settings=self.settings,
        )

    def get_history(self, tool_id: str | None = None) -> list[dict[str, Any]]:
        """Get pipeline execution history, optionally filtered by tool_id."""
        if tool_id is None:
            return list(self._history)
        return [h for h in self._history if h.get("tool_id") == tool_id]

    def get_latest(self, tool_id: str) -> dict[str, Any] | None:
        """Get the latest pipeline result for a tool."""
        history = self.get_history(tool_id)
        return history[-1] if history else None

    def status(self) -> dict[str, Any]:
        """Return pipeline status summary."""
        return {
            "total_runs": len(self._history),
            "successful": sum(1 for h in self._history if h.get("success")),
            "failed": sum(1 for h in self._history if not h.get("success")),
            "tools_processed": len({h.get("tool_id") for h in self._history}),
            "confidence_threshold": self.confidence_threshold,
            "components": {
                "mapper": self.mapper is not None,
                "store": self.store is not None,
                "retriever": self.retriever is not None,
                "auditor": self.auditor is not None,
                "provider_registry": self.provider_registry is not None,
            },
        }
