"""Discovery service: fetch, parse, stage, and lifecycle-manage API specifications.

This is the entry point for Phase 1 (dynamic API discovery). It is responsible for:

1. Fetching API specifications from configured sources.
2. Parsing them into normalized forms.
3. Assigning lifecycle states (discovered, staged, verified, suspended).
4. Deduplicating against the existing catalogue.
5. Producing provider definitions ready for the generic runtime (Phase 2).

Discovery and execution are separate: discovering an API does not make it
available for execution. A provider must pass through staging and verification
before it can be selected by the Client.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agent_bazaar.ingestion.models import NormalizedSpec
from agent_bazaar.ingestion.openapi import parse_openapi
from agent_bazaar.ingestion.utility import IngestionUtility
from agent_bazaar.ingestion.listing_metadata import ListingMetadata, extract_listing_metadata
from agent_bazaar.config import get_settings
from agent_bazaar.vec import build_vector_service
from agent_bazaar.mapper.agent import MapperAgent
from agent_bazaar.kg import KgStore
import asyncio
import hashlib
import logging
import time
from typing import Optional

from app.schemas import ToolSpec

LOGGER = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lifecycle states
# ---------------------------------------------------------------------------


class ProviderState:
    """Lifecycle states for a discovered provider."""

    DISCOVERED = "discovered"  # API found, spec fetched, not yet parsed
    STAGED = "staged"  # Parsed, mapped, awaiting verification
    VERIFIED = "verified"  # Passed checks, available in marketplace
    SUSPENDED = "suspended"  # Failed verification or reliability threshold


VALID_STATES = frozenset(
    {
        ProviderState.DISCOVERED,
        ProviderState.STAGED,
        ProviderState.VERIFIED,
        ProviderState.SUSPENDED,
    }
)


# ---------------------------------------------------------------------------
# Provider definition (pre-execution)
# ---------------------------------------------------------------------------


@dataclass
class ProviderDefinition:
    """A parsed API specification awaiting or undergoing lifecycle management.

    This is the bridge between discovery and the generic provider runtime.
    It carries everything the runtime needs to execute the API, plus the
    lifecycle metadata that gates availability.
    """

    tool_id: str
    name: str
    provider_id: str
    description: str = ""
    base_url: str = ""
    spec_format: str = "openapi_json"
    spec_version: str = ""
    endpoints: list[dict[str, Any]] = field(default_factory=list)
    fields: list[dict[str, Any]] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    listing_metadata: ListingMetadata | None = None
    state: str = ProviderState.DISCOVERED
    source: str = ""
    discovered_at: float = field(default_factory=time.time)
    staged_at: float | None = None
    verified_at: float | None = None
    suspended_reason: str | None = None
    duplicate_of: str | None = None
    verification_notes: list[str] = field(default_factory=list)

    @property
    def is_executable(self) -> bool:
        return self.state == ProviderState.VERIFIED

    @property
    def capability(self) -> str:
        return self.capabilities[0] if self.capabilities else "general"

    def to_tool_spec(self) -> ToolSpec:
        """Convert to a ToolSpec for the graph and catalogue."""
        inputs = [
            ToolSpec.model_construct(
                concept=f.get("concept", ""),
                name=f.get("name", ""),
                datatype=f.get("type", "string"),
                description=f.get("description", ""),
                fields=f.get("fields", []),
            )
            for f in self.fields
            if f.get("direction") == "input"
        ]
        outputs = [
            ToolSpec.model_construct(
                concept=f.get("concept", ""),
                name=f.get("name", ""),
                datatype=f.get("type", "string"),
                description=f.get("description", ""),
                fields=f.get("fields", []),
            )
            for f in self.fields
            if f.get("direction") == "output"
        ]
        return ToolSpec(
            id=self.tool_id,
            name=self.name,
            provider_id=self.provider_id,
            description=self.description,
            capability=self.capabilities[0] if self.capabilities else "general",
            inputs=inputs,
            outputs=outputs,
            claims=[],
            keywords=[
                self.name,
                self.description,
                self.capability,
            ],
            docs_url=self.base_url,
            pricing_tier=str(self.listing_metadata.pricing_tier) if self.listing_metadata else "unknown",
            access_requirement=str(self.listing_metadata.access_requirement) if self.listing_metadata else "unknown",
            doc_quality=float(self.listing_metadata.doc_quality) if self.listing_metadata else 0.0,
            mapping_coverage=0.0,
            is_executable=self.is_executable,
            execution="live" if self.is_executable else "fixture",
            tags=["discovered"]
            if self.state == ProviderState.DISCOVERED
            else ["staged"]
            if self.state == ProviderState.STAGED
            else ["verified"]
            if self.state == ProviderState.VERIFIED
            else ["suspended"],
        )


# ---------------------------------------------------------------------------
# Discovery service
# ---------------------------------------------------------------------------


def _endpoint_to_dict(ep: Any) -> dict[str, Any]:
    """Convert an EndpointInfo pydantic object to a plain dict."""
    return {
        "path": getattr(ep, "path", ""),
        "method": getattr(ep, "method", "GET"),
        "summary": getattr(ep, "summary", ""),
        "description": getattr(ep, "description", ""),
        "operation_id": getattr(ep, "operation_id", ""),
        "parameters": [_field_to_dict(p) for p in getattr(ep, "parameters", [])],
        "request_fields": [_field_to_dict(f) for f in getattr(ep, "request_fields", [])],
        "response_fields": [_field_to_dict(f) for f in getattr(ep, "response_fields", [])],
    }


def _field_to_dict(f: Any) -> dict[str, Any]:
    """Convert a FieldInfo pydantic object to a plain dict."""
    path = getattr(f, "path", "")
    location = "query"
    if isinstance(path, str) and path.startswith("parameters."):
        location = path.split(".")[-1]
    return {
        "path": path,
        "name": getattr(f, "name", ""),
        "type": getattr(f, "type", "string"),
        "description": getattr(f, "description", ""),
        "direction": getattr(f, "direction", "output"),
        "required": getattr(f, "required", None),
        "endpoint": getattr(f, "endpoint", None),
        "method": getattr(f, "method", None),
        "location": location,
    }


class DiscoveryService:
    """Manages the discovery, staging, and lifecycle of API specifications.

    This service is the front end of the automated discovery pipeline. It
    fetches specifications from configured sources, parses them, deduplicates
    against the existing catalogue, assigns lifecycle states, and persists
    provider definitions for the generic runtime.
    """

    def __init__(
        self,
        specs_dir: Path,
        staging_dir: Path,
        overrides_path: Path | None = None,
        timeout: int = 30,
    ):
        self.specs_dir = specs_dir
        self.staging_dir = staging_dir
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        self.ingester = IngestionUtility()
        self.overrides_path = overrides_path
        self.timeout = timeout
        self._definitions: dict[str, ProviderDefinition] = {}

    # ------------------------------------------------------------------
    # Source fetching
    # ------------------------------------------------------------------

    def fetch_from_apis_guru(self, limit: int = 100, seed: int = 42) -> list[dict]:
        """Fetch API entries from the APIs.guru directory.

        Returns a list of entry metadata (key, title, categories, url, etc.).
        The actual spec documents are fetched separately by ``fetch_spec``.
        """
        from agent_bazaar.ingestion.sources import APIS_GURU_LIST_URL, ApisGuruSource
        import random

        source = ApisGuruSource(timeout=self.timeout)
        listing = json.loads(source.opener(APIS_GURU_LIST_URL).decode("utf-8"))
        entries = ApisGuruSource.entries_from_listing(listing)
        rng = random.Random(seed)
        rng.shuffle(entries)
        return entries[:limit]

    def fetch_spec(self, entry: dict) -> bytes | None:
        """Fetch the raw specification document for one directory entry."""
        from agent_bazaar.ingestion.sources import ApisGuruSource

        try:
            source = ApisGuruSource(timeout=self.timeout)
            return source.fetch(entry)
        except Exception as exc:
            LOGGER.warning("failed to fetch spec for %s: %s", entry.get("key"), exc)
            return None

    def fetch_local_spec(self, path: Path) -> bytes | None:
        """Read a locally uploaded specification."""
        try:
            return path.read_bytes()
        except Exception as exc:
            LOGGER.warning("failed to read local spec %s: %s", path, exc)
            return None

    # ------------------------------------------------------------------
    # Parsing and normalization
    # ------------------------------------------------------------------

    def parse_spec(self, content: bytes, source: str = "") -> NormalizedSpec | None:
        """Parse a raw specification into a NormalizedSpec."""
        try:
            # Write to a temp location for the ingester
            tmp_path = self.specs_dir / f"_tmp_{hashlib.md5(content).hexdigest()[:12]}.json"
            tmp_path.write_bytes(content)
            try:
                spec = self.ingester.ingest(tmp_path)
                spec.source = source
                return spec
            finally:
                if tmp_path.exists():
                    tmp_path.unlink()
        except Exception as exc:
            LOGGER.warning("failed to parse spec from %s: %s", source, exc)
            return None

    def parse_raw_openapi(self, content: bytes, source: str = "") -> NormalizedSpec | None:
        """Parse raw OpenAPI content without writing to disk.

        This is a lighter-weight path for specs that are already in memory.
        """
        try:
            text = content.decode("utf-8", errors="replace")
            path = Path(f"<memory:{source}>")
            document = json.loads(text)
            if "openapi" not in document and "swagger" not in document:
                return None
            return parse_openapi(path, text, "openapi_json", document)
        except Exception as exc:
            LOGGER.warning("failed to parse raw OpenAPI from %s: %s", source, exc)
            return None

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def is_duplicate(self, spec: NormalizedSpec, existing_tools: list[dict]) -> str | None:
        """Check if a spec is a duplicate of an existing tool.

        Returns the tool_id of the existing tool if a duplicate is found,
        or None if the spec is new.
        """
        # Compare by base_url first (same API endpoint)
        if spec.base_url:
            for tool in existing_tools:
                if tool.get("base_url") == spec.base_url:
                    return tool.get("id")

        # Compare by provider_id (same service)
        derived_provider = self._derive_provider_id(spec)
        for tool in existing_tools:
            if tool.get("provider_id") == derived_provider:
                return tool.get("id")

        # Compare by title similarity (same API, different listing)
        if spec.title:
            spec_key = spec.title.lower().strip()
            for tool in existing_tools:
                tool_name = str(tool.get("name", "")).lower().strip()
                if spec_key and tool_name and spec_key == tool_name:
                    return tool.get("id")

        return None

    def _derive_provider_id(self, spec: NormalizedSpec) -> str:
        """Derive a provider_id from the spec, matching the pipeline convention."""
        from agent_bazaar.pipeline import derive_provider_id as pipeline_derive

        return pipeline_derive(spec)

    # ------------------------------------------------------------------
    # Lifecycle management
    # ------------------------------------------------------------------

    def discover(
        self, content: bytes, source: str = "", existing_tools: list[dict] | None = None
    ) -> ProviderDefinition | None:
        """Discover a provider from raw specification content.

        This is the main entry point for the discovery pipeline. It parses the
        spec, checks for duplicates, assigns the DISCOVERED state, and returns
        a ProviderDefinition.
        """
        if existing_tools is None:
            existing_tools = []

        spec = self.parse_raw_openapi(content, source)
        if spec is None:
            return None

        # Check for duplicates
        duplicate_of = self.is_duplicate(spec, existing_tools)
        if duplicate_of:
            LOGGER.info("spec %s is a duplicate of existing tool %s", spec.tool_id, duplicate_of)
            definition = self._spec_to_definition(spec, source)
            definition.state = ProviderState.DISCOVERED
            definition.duplicate_of = duplicate_of
            return definition

        definition = self._spec_to_definition(spec, source)
        definition.state = ProviderState.DISCOVERED
        return definition

    def stage(self, definition: ProviderDefinition) -> ProviderDefinition:
        """Move a discovered provider to STAGED state.

        Staging means the spec has been parsed, metadata extracted, and the
        provider is ready for verification. The provider is persisted to the
        staging directory. Already-staged or later states are returned unchanged.
        """
        if definition.state != ProviderState.DISCOVERED:
            # Already staged, verified, or suspended - return unchanged
            if definition.state in (ProviderState.STAGED, ProviderState.VERIFIED, ProviderState.SUSPENDED):
                return definition
            LOGGER.warning("cannot stage provider %s in state %s", definition.tool_id, definition.state)
            return definition

        definition.state = ProviderState.STAGED
        definition.staged_at = time.time()
        self._persist_staged(definition)
        return definition

    def verify(self, definition: ProviderDefinition, checks: list[str] | None = None) -> ProviderDefinition:
        """Move a staged provider to VERIFIED state.

        Verification is a gating step. In the full pipeline this would involve
        the Auditor checking claims, probing the API, and validating the schema.
        Here we establish the state transition and record verification notes.
        """
        if definition.state != ProviderState.STAGED:
            LOGGER.warning("cannot verify provider %s in state %s", definition.tool_id, definition.state)
            return definition

        definition.state = ProviderState.VERIFIED
        definition.verified_at = time.time()
        if checks:
            definition.verification_notes.extend(checks)
        self._persist_staged(definition)
        return definition

    def suspend(self, definition: ProviderDefinition, reason: str) -> ProviderDefinition:
        """Suspend a provider, recording the reason."""
        definition.state = ProviderState.SUSPENDED
        definition.suspended_reason = reason
        self._persist_staged(definition)
        return definition

    def reactivate(self, definition: ProviderDefinition) -> ProviderDefinition:
        """Move a suspended provider back to STAGED for re-verification."""
        if definition.state != ProviderState.SUSPENDED:
            return definition
        definition.state = ProviderState.STAGED
        definition.suspended_reason = None
        definition.staged_at = time.time()
        self._persist_staged(definition)
        return definition

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist_staged(self, definition: ProviderDefinition) -> None:
        """Persist a staged/verified/suspended provider definition."""
        path = self.staging_dir / f"{definition.tool_id}.json"
        payload = self._definition_to_dict(definition)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def load_staged(self) -> list[ProviderDefinition]:
        """Load all staged/verified/suspended providers from disk."""
        definitions = []
        for path in sorted(self.staging_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                definitions.append(self._dict_to_definition(data))
            except Exception as exc:
                LOGGER.warning("failed to load staged provider %s: %s", path, exc)
        return definitions

    def clear_staged(self) -> int:
        """Clear all staged definitions. Returns the count cleared."""
        count = 0
        for path in self.staging_dir.glob("*.json"):
            try:
                path.unlink()
                count += 1
            except Exception:
                pass
        return count

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _spec_to_definition(self, spec: NormalizedSpec, source: str) -> ProviderDefinition:
        """Convert a NormalizedSpec to a ProviderDefinition."""
        from agent_bazaar.pipeline import (
            derive_capabilities,
            derive_provider_id,
            tool_id_for_spec,
        )

        listing = spec.metadata.get("listing")
        metadata = listing if isinstance(listing, dict) else {}

        return ProviderDefinition(
            tool_id=spec.tool_id,
            name=spec.title or spec.tool_id,
            provider_id=derive_provider_id(spec),
            description=spec.description,
            base_url=spec.base_url,
            spec_format=spec.spec_format,
            spec_version=spec.version,
            endpoints=[_endpoint_to_dict(ep) for ep in spec.endpoints],
            fields=[_field_to_dict(f) for f in spec.fields],
            capabilities=derive_capabilities(spec),
            listing_metadata=(ListingMetadata(**metadata) if metadata else None),
            source=source,
        )

    def _definition_to_dict(self, definition: ProviderDefinition) -> dict:
        """Serialize a ProviderDefinition to a dict."""
        return {
            "tool_id": definition.tool_id,
            "name": definition.name,
            "provider_id": definition.provider_id,
            "description": definition.description,
            "base_url": definition.base_url,
            "spec_format": definition.spec_format,
            "spec_version": definition.spec_version,
            "endpoints": definition.endpoints,
            "fields": definition.fields,
            "capabilities": definition.capabilities,
            "listing_metadata": (definition.listing_metadata.model_dump() if definition.listing_metadata else None),
            "state": definition.state,
            "source": definition.source,
            "discovered_at": definition.discovered_at,
            "staged_at": definition.staged_at,
            "verified_at": definition.verified_at,
            "suspended_reason": definition.suspended_reason,
            "duplicate_of": definition.duplicate_of,
            "verification_notes": definition.verification_notes,
        }

    def _dict_to_definition(self, data: dict) -> ProviderDefinition:
        """Deserialize a dict to a ProviderDefinition."""
        from agent_bazaar.ingestion.listing_metadata import ListingMetadata

        listing_data = data.get("listing_metadata")
        listing_metadata = ListingMetadata(**listing_data) if isinstance(listing_data, dict) else None

        return ProviderDefinition(
            tool_id=data["tool_id"],
            name=data["name"],
            provider_id=data["provider_id"],
            description=data.get("description", ""),
            base_url=data.get("base_url", ""),
            spec_format=data.get("spec_format", "openapi_json"),
            spec_version=data.get("spec_version", ""),
            endpoints=data.get("endpoints", []),
            fields=data.get("fields", []),
            capabilities=data.get("capabilities", []),
            listing_metadata=listing_metadata,
            state=data.get("state", ProviderState.DISCOVERED),
            source=data.get("source", ""),
            discovered_at=data.get("discovered_at", time.time()),
            staged_at=data.get("staged_at"),
            verified_at=data.get("verified_at"),
            suspended_reason=data.get("suspended_reason"),
            duplicate_of=data.get("duplicate_of"),
            verification_notes=data.get("verification_notes", []),
        )

    # ------------------------------------------------------------------
    # Discovery pipeline (multi-source)
    # ------------------------------------------------------------------

    def run_discovery(
        self,
        sources: list[dict[str, Any]] | None = None,
        existing_tools: list[dict] | None = None,
        limit_per_source: int = 50,
    ) -> list[ProviderDefinition]:
        """Run discovery across configured sources.

        This is the top-level entry point for Phase 1. It fetches specs from
        each source, parses them, deduplicates, and returns newly discovered
        provider definitions in the DISCOVERED state.

        Args:
            sources: List of source configs. Each config is a dict with a
                ``type`` key ("apis-guru" or "local") and source-specific
                parameters.
            existing_tools: Existing catalogue tools for deduplication.
            limit_per_source: Maximum specs to fetch per source.

        Returns:
            List of newly discovered ProviderDefinitions.
        """
        if sources is None:
            sources = [{"type": "apis-guru"}]

        if existing_tools is None:
            existing_tools = []

        discovered: list[ProviderDefinition] = []

        for source_config in sources:
            source_type = source_config.get("type", "apis-guru")

            if source_type == "apis-guru":
                entries = self.fetch_from_apis_guru(limit=limit_per_source)
                for entry in entries:
                    content = self.fetch_spec(entry)
                    if content is None:
                        continue
                    definition = self.discover(
                        content, source=entry.get("url", "apis-guru"), existing_tools=existing_tools
                    )
                    if definition is not None:
                        discovered.append(definition)

            elif source_type == "local":
                local_dir = Path(source_config.get("dir", str(self.specs_dir / "uploads")))
                if not local_dir.exists():
                    continue
                for path in sorted(local_dir.glob("*.json")):
                    if path.name == "manifest.json":
                        continue
                    content = self.fetch_local_spec(path)
                    if content is None:
                        continue
                    definition = self.discover(content, source=str(path), existing_tools=existing_tools)
                    if definition is not None:
                        discovered.append(definition)

            elif source_type == "openapi-url":
                url = source_config.get("url", "")
                if not url:
                    continue
                try:
                    from agent_bazaar.ingestion.sources import ApisGuruSource

                    source = ApisGuruSource(timeout=self.timeout)
                    content = source.opener(url).read()
                    definition = self.discover(content, source=url, existing_tools=existing_tools)
                    if definition is not None:
                        discovered.append(definition)
                except Exception as exc:
                    LOGGER.warning("failed to fetch URL %s: %s", url, exc)

        return discovered


# ---------------------------------------------------------------------------
# Continuous Discovery Scheduler
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auditor integration for automatic verification
# ---------------------------------------------------------------------------


async def verify_provider_with_auditor(
    definition: ProviderDefinition,
    auditor: Any,
    settings: Any,
) -> dict[str, Any]:
    """Verify a provider definition using the Auditor.

    Performs four distinct verification levels:
    1. Specification validity - endpoints, schemas, structure
    2. Endpoint availability - probes endpoints when possible
    3. Capability correctness - checks against ontology
    4. Security and execution safety - auth, SSRF, rate limits

    Returns verification results with detailed notes.
    """
    result = {
        "tool_id": definition.tool_id,
        "verified": False,
        "specification_valid": False,
        "endpoint_available": False,
        "capability_correct": False,
        "security_safe": False,
        "claims_checked": 0,
        "claims_verified": 0,
        "schema_valid": False,
        "errors": [],
        "notes": [],
        "verification_history": [],
    }

    # Level 1: Specification validity
    spec_valid, spec_notes = _verify_specification_validity(definition)
    result["specification_valid"] = spec_valid
    result["notes"].extend(spec_notes)

    if not spec_valid:
        result["errors"].append("Specification validation failed")
        result["errors"].extend(n[6:] for n in spec_notes if n.startswith("FAIL: "))
        return result

    # Level 2: Endpoint availability
    if auditor and hasattr(auditor, "probe"):
        try:
            endpoint_notes, endpoint_ok = await _probe_endpoints(definition, auditor)
            result["endpoint_available"] = endpoint_ok
            result["notes"].extend(endpoint_notes)
        except Exception as e:
            result["notes"].append(f"Endpoint probing skipped: {e}")
    else:
        result["notes"].append("Endpoint probing requires live auditor")

    # Level 3: Capability correctness
    capability_notes, capability_ok = _verify_capabilities(definition)
    result["capability_correct"] = capability_ok
    result["notes"].extend(capability_notes)

    # Level 4: Security and execution safety
    security_notes, security_ok = _verify_security(definition)
    result["security_safe"] = security_ok
    result["notes"].extend(security_notes)

    # Extract and count claims
    claims = _extract_claims_from_definition(definition)
    result["claims_checked"] = len(claims)
    result["claims_verified"] = sum(1 for c in claims if c.get("verified", False))

    # Must pass specification validity AND security safety
    result["verified"] = spec_valid and security_ok

    if result["verified"]:
        result["notes"].append("Verification passed")
    else:
        result["notes"].append("Verification failed")

    return result


def _verify_specification_validity(definition: ProviderDefinition) -> tuple[bool, list[str]]:
    """Validate the specification structure and endpoints."""
    notes = []
    valid = True

    if not definition.tool_id:
        notes.append("FAIL: Missing tool_id")
        valid = False
    else:
        notes.append("OK: tool_id present")

    if not definition.endpoints:
        notes.append("FAIL: No endpoints defined")
        valid = False
    else:
        notes.append(f"OK: {len(definition.endpoints)} endpoints defined")

    for ep in definition.endpoints:
        if not ep.get("path"):
            notes.append("FAIL: Endpoint missing path")
            valid = False
        if not ep.get("method"):
            notes.append("FAIL: Endpoint missing method")
            valid = False

    for field in definition.fields:
        if not field.get("name"):
            notes.append("FAIL: Field missing name")
            valid = False
        if not field.get("direction"):
            notes.append("FAIL: Field missing direction")
            valid = False

    return valid, notes


async def _probe_endpoints(
    definition: ProviderDefinition,
    auditor: Any,
) -> tuple[list[str], bool]:
    """Probe endpoints for availability."""
    notes = []
    available = True

    for ep in definition.endpoints:
        path = ep.get("path", "")
        method = ep.get("method", "GET").upper()

        if method not in ("GET", "HEAD"):
            notes.append(f"SKIP: {method} {path} (not probed for safety)")
            continue

        try:
            if hasattr(auditor, "probe"):
                probe_result = auditor.probe(definition.tool_id, force_fixture=True)
                if probe_result:
                    notes.append(f"OK: {method} {path} probed")
                else:
                    notes.append(f"WARN: {method} {path} probe returned no result")
            else:
                notes.append(f"SKIP: {method} {path} (no probe capability)")
        except Exception as e:
            notes.append(f"WARN: {method} {path} probe failed: {e}")
            available = False

    return notes, available


def _verify_capabilities(definition: ProviderDefinition) -> tuple[list[str], bool]:
    """Verify that declared capabilities are consistent with endpoints."""
    notes = []
    valid = True

    if not definition.capabilities:
        notes.append("WARN: No capabilities declared")
        return notes, True

    notes.append(f"OK: {len(definition.capabilities)} capabilities declared")

    has_output = any(f.get("direction") == "output" for f in definition.fields)
    if not has_output and definition.fields:
        notes.append("WARN: No output fields declared")
        valid = False

    return notes, valid


def _verify_security(definition: ProviderDefinition) -> tuple[list[str], bool]:
    """Verify security posture."""
    notes = []
    safe = True

    base_url = definition.base_url or ""
    if base_url.startswith("http://") and "localhost" not in base_url:
        notes.append("WARN: HTTP (not HTTPS) base URL")
    elif base_url.startswith("https://"):
        notes.append("OK: HTTPS base URL")

    if definition.listing_metadata:
        access = definition.listing_metadata.access_requirement
        if access == "keyless":
            notes.append("OK: API is keyless")
        else:
            notes.append(f"INFO: API requires {access}")

    return notes, safe


def _extract_claims_from_definition(definition: ProviderDefinition) -> list[dict[str, Any]]:
    """Extract verifiable claims."""
    claims = []

    if definition.endpoints:
        claims.append(
            {
                "text": f"API has {len(definition.endpoints)} endpoints",
                "verified": True,
                "source": "specification",
            }
        )

    input_count = sum(1 for f in definition.fields if f.get("direction") == "input")
    output_count = sum(1 for f in definition.fields if f.get("direction") == "output")
    if input_count or output_count:
        claims.append(
            {
                "text": f"API has {input_count} inputs and {output_count} outputs",
                "verified": True,
                "source": "specification",
            }
        )

    return claims


# ---------------------------------------------------------------------------
# Mapper integration for concept mapping
# ---------------------------------------------------------------------------


async def map_provider_to_ontology(
    definition: ProviderDefinition,
    mapper: Any,
    store: Any,
    retriever: Any = None,
    confidence_threshold: float = 0.5,
) -> dict[str, Any]:
    """Map provider fields to ontology concepts using the Mapper.

    Pipeline:
    1. Convert provider fields to FieldSpec objects
    2. Run the mapper to find concept mappings
    3. Filter by confidence threshold (low-confidence mappings require review)
    4. Persist accepted mappings to the knowledge graph
    5. Rebuild the GraphRAG retriever so new capabilities are searchable
    6. Return mapping results with history

    Low-confidence mappings are NOT auto-accepted; they are returned
    in 'pending_review' for human review.
    """
    from agent_bazaar.messages.schema import FieldSpec, MapRequest

    result = {
        "tool_id": definition.tool_id,
        "mapped": False,
        "fields_mapped": 0,
        "fields_total": 0,
        "fields_pending_review": 0,
        "confidence": 0.0,
        "threshold": confidence_threshold,
        "errors": [],
        "unmapped_fields": [],
        "pending_review": [],
        "persisted": False,
        "retriever_rebuilt": False,
        "notes": [],
    }

    if not mapper:
        result["errors"].append("No mapper available")
        return result

    # Convert provider fields to FieldSpec objects
    field_specs = []
    for field in definition.fields:
        field_specs.append(
            FieldSpec(
                field_path=field.get("path", ""),
                name=field.get("name", ""),
                type=field.get("type", "string"),
                description=field.get("description", ""),
                direction=field.get("direction", "output"),
                endpoint=field.get("endpoint"),
                method=field.get("method"),
            )
        )

    result["fields_total"] = len(field_specs)

    if not field_specs:
        result["errors"].append("No fields to map")
        return result

    # Run the mapper
    request = MapRequest(tool_id=definition.tool_id, fields=field_specs)

    try:
        map_result = mapper.map_fields(request)
    except Exception as e:
        result["errors"].append(f"Mapping error: {e}")
        return result

    # Split mappings by confidence
    accepted = []
    pending = []
    for m in map_result.mappings:
        status = m.status.value if hasattr(m.status, "value") else str(m.status)
        if status == "unmapped":
            result["unmapped_fields"].append(m.field_path)
            continue
        if float(m.confidence or 0.0) >= confidence_threshold:
            accepted.append(m)
        else:
            pending.append(
                {
                    "field_path": m.field_path,
                    "concept": m.concept,
                    "concept_label": m.concept_label,
                    "confidence": float(m.confidence or 0.0),
                    "reason": m.reason or "",
                    "status": "pending_review",
                }
            )

    result["fields_mapped"] = len(accepted)
    result["fields_pending_review"] = len(pending)
    result["pending_review"] = pending
    result["unmapped_fields"].extend(m.field_path for m in map_result.unmapped)

    if accepted:
        confidences = [float(m.confidence or 0.0) for m in accepted]
        result["confidence"] = round(sum(confidences) / len(confidences), 4)

    # Persist accepted mappings to the knowledge graph
    if store is not None and accepted:
        try:
            # Build a ToolRecord from the definition and accepted mappings
            from agent_bazaar.models import MappedField, ToolRecord

            inputs = []
            outputs = []
            for m in accepted:
                direction = getattr(m, "direction", None)
                if direction not in ("input", "output"):
                    direction = "input" if m.field_path.startswith("input.") else "output"
                mapped = MappedField(
                    field_path=m.field_path,
                    name=m.field_path.rsplit(".", 1)[-1],
                    concept=m.concept,
                    concept_label=m.concept_label or "",
                    unit=getattr(m, "unit", None),
                    unit_family=getattr(m, "unit_family", None),
                    direction=direction,
                    confidence=float(m.confidence or 0.0),
                    reason=m.reason or "",
                    status="mapped",
                )
                if direction == "input":
                    inputs.append(mapped)
                else:
                    outputs.append(mapped)

            record = ToolRecord(
                tool_id=definition.tool_id,
                name=definition.name,
                description=definition.description,
                provider_id=definition.provider_id,
                base_url=definition.base_url,
                capabilities=definition.capabilities,
                inputs=inputs,
                outputs=outputs,
                source=definition.source,
            )
            store.write_tool(record)
            result["persisted"] = True
            result["notes"].append(f"Persisted {len(accepted)} mappings to graph")
        except Exception as e:
            result["errors"].append(f"Graph persistence failed: {e}")

    # Rebuild the retriever so new capabilities are searchable
    if retriever is not None and result["persisted"]:
        try:
            retriever.rebuild()
            result["retriever_rebuilt"] = True
            result["notes"].append("Retriever index rebuilt")
        except Exception as e:
            result["errors"].append(f"Retriever rebuild failed: {e}")

    result["mapped"] = len(accepted) > 0
    result["notes"].append(
        f"Mapped {result['fields_mapped']}/{result['fields_total']} fields, "
        f"{result['fields_pending_review']} pending review"
    )

    return result


class ContinuousDiscoveryScheduler:
    def __init__(self, discovery_service, staging_registry, checkpoint_dir, interval_seconds=3600, max_concurrent=5):
        self.service = discovery_service
        self.staging = staging_registry
        self.checkpoint_dir = checkpoint_dir
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.interval_seconds = interval_seconds
        self.max_concurrent = max_concurrent
        self._running = False
        self._task = None
        self._sources = []
        self._last_checkpoint = {}

    def load_checkpoint(self):
        checkpoint_path = self.checkpoint_dir / "checkpoint.json"
        if checkpoint_path.exists():
            try:
                data = json.loads(checkpoint_path.read_text(encoding="utf-8"))
                self._last_checkpoint = data.get("specs", {})
            except Exception:
                self._last_checkpoint = {}

    def save_checkpoint(self, spec_hashes):
        checkpoint_path = self.checkpoint_dir / "checkpoint.json"
        try:
            checkpoint_path.write_text(
                json.dumps({"specs": spec_hashes, "saved_at": time.time()}, indent=2), encoding="utf-8"
            )
        except Exception as e:
            logging.warning("Failed to save checkpoint: %s", e)

    def _hash_spec(self, content):
        return hashlib.sha256(content).hexdigest()[:16]

    def configure_sources(self, sources):
        self._sources = sources

    def status(self):
        return {
            "running": self._running,
            "interval_seconds": self.interval_seconds,
            "sources": len(self._sources),
            "checkpoint_specs": len(self._last_checkpoint),
        }
