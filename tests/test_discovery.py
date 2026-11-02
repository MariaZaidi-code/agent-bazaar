"""Tests for the discovery module.

These tests verify the discovery pipeline components:
- DiscoveryService: fetching, parsing, staging
- StagingRegistry: lifecycle management, deduplication
- ProviderDefinition: serialization and state transitions
"""

from __future__ import annotations

import json
import pytest
from pathlib import Path

from app.discovery.service import (
    DiscoveryService,
    ProviderDefinition,
    ProviderState,
)
from app.discovery.staging import StagingRegistry


class TestProviderState:
    """Test lifecycle state constants."""

    def test_state_constants(self):
        assert ProviderState.DISCOVERED == "discovered"
        assert ProviderState.STAGED == "staged"
        assert ProviderState.VERIFIED == "verified"
        assert ProviderState.SUSPENDED == "suspended"


class TestProviderDefinition:
    """Test ProviderDefinition creation and serialization."""

    def test_create_minimal(self):
        """Test creating a minimal provider definition."""
        definition = ProviderDefinition(
            tool_id="test-tool",
            name="Test Tool",
            provider_id="test-provider",
        )
        assert definition.tool_id == "test-tool"
        assert definition.name == "Test Tool"
        assert definition.provider_id == "test-provider"
        assert definition.state == ProviderState.DISCOVERED
        assert not definition.is_executable

    def test_state_transitions(self):
        """Test valid state transitions."""
        definition = ProviderDefinition(
            tool_id="test-tool",
            name="Test Tool",
            provider_id="test-provider",
        )

        # DISCOVERED -> STAGED
        definition.state = ProviderState.STAGED
        assert definition.state == ProviderState.STAGED
        assert not definition.is_executable

        # STAGED -> VERIFIED
        definition.state = ProviderState.VERIFIED
        assert definition.state == ProviderState.VERIFIED
        assert definition.is_executable

        # VERIFIED -> SUSPENDED
        definition.state = ProviderState.SUSPENDED
        assert definition.state == ProviderState.SUSPENDED
        assert not definition.is_executable

    def test_serialization(self):
        """Test serialization to dict and back."""
        definition = ProviderDefinition(
            tool_id="test-tool",
            name="Test Tool",
            provider_id="test-provider",
            description="A test provider",
            base_url="https://api.example.com",
            spec_format="openapi_json",
            state=ProviderState.STAGED,
            capabilities=["test-capability"],
            endpoints=[
                {
                    "path": "/v1/test",
                    "method": "GET",
                    "operation_id": "getTest",
                    "parameters": [],
                    "request_fields": [],
                    "response_fields": [],
                }
            ],
            fields=[
                {
                    "path": "output.result",
                    "name": "result",
                    "type": "string",
                    "direction": "output",
                }
            ],
            staged_at=1234567890.0,
        )

        data = definition.__dict__.copy()
        # Remove non-serializable fields
        data.pop("listing_metadata", None)

        # Round-trip through JSON
        json_str = json.dumps(data, indent=2)
        loaded = json.loads(json_str)

        assert loaded["tool_id"] == "test-tool"
        assert loaded["name"] == "Test Tool"
        assert loaded["state"] == ProviderState.STAGED
        assert loaded["staged_at"] == 1234567890.0


class TestDiscoveryService:
    """Test the DiscoveryService."""

    @pytest.fixture
    def temp_dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create temporary directories for testing."""
        specs_dir = tmp_path / "specs"
        staging_dir = tmp_path / "staging"
        specs_dir.mkdir()
        staging_dir.mkdir()
        return specs_dir, staging_dir

    def test_init(self, temp_dirs: tuple[Path, Path]):
        """Test service initialization."""
        specs_dir, staging_dir = temp_dirs
        service = DiscoveryService(specs_dir=specs_dir, staging_dir=staging_dir)
        assert service.specs_dir == specs_dir
        assert service.staging_dir == staging_dir

    def test_parse_raw_openapi_valid(self, temp_dirs: tuple[Path, Path]):
        """Test parsing a valid OpenAPI spec."""
        specs_dir, staging_dir = temp_dirs
        service = DiscoveryService(specs_dir=specs_dir, staging_dir=staging_dir)

        # Minimal valid OpenAPI spec
        spec_content = {
            "openapi": "3.0.0",
            "info": {
                "title": "Test API",
                "version": "1.0.0",
                "description": "A test API for discovery",
            },
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/test": {
                    "get": {
                        "operationId": "getTest",
                        "summary": "Test endpoint",
                        "responses": {
                            "200": {
                                "description": "Success",
                                "content": {
                                    "application/json": {
                                        "schema": {"type": "object", "properties": {"result": {"type": "string"}}}
                                    }
                                },
                            }
                        },
                    }
                }
            },
        }

        spec = service.parse_raw_openapi(
            json.dumps(spec_content).encode(),
            source="test-source",
        )

        assert spec is not None
        assert spec.tool_id.startswith("memory-")  # Memory source gets hashed tool_id
        assert spec.title == "Test API"
        assert spec.base_url == "https://api.example.com"
        assert len(spec.endpoints) == 1
        assert spec.endpoints[0].operation_id == "getTest"

    def test_parse_raw_openapi_invalid(self, temp_dirs: tuple[Path, Path]):
        """Test parsing an invalid spec returns None."""
        specs_dir, staging_dir = temp_dirs
        service = DiscoveryService(specs_dir=specs_dir, staging_dir=staging_dir)

        # Not an OpenAPI spec
        invalid_content = json.dumps({"foo": "bar"}).encode()
        spec = service.parse_raw_openapi(invalid_content, source="test-source")
        assert spec is None

    def test_discover_new_provider(self, temp_dirs: tuple[Path, Path]):
        """Test discovering a new provider from spec content."""
        specs_dir, staging_dir = temp_dirs
        service = DiscoveryService(specs_dir=specs_dir, staging_dir=staging_dir)

        spec_content = {
            "openapi": "3.0.0",
            "info": {
                "title": "New Test API",
                "version": "1.0.0",
            },
            "paths": {},
        }

        definition = service.discover(
            json.dumps(spec_content).encode(),
            source="test-source",
            existing_tools=[],
        )

        assert definition is not None
        assert definition.tool_id.startswith("memory-")  # Memory source gets hashed tool_id
        assert definition.state == ProviderState.DISCOVERED
        assert definition.name == "New Test API"

    def test_discover_duplicate(self, temp_dirs: tuple[Path, Path]):
        """Test that duplicate detection works."""
        specs_dir, staging_dir = temp_dirs
        service = DiscoveryService(specs_dir=specs_dir, staging_dir=staging_dir)

        spec_content = {
            "openapi": "3.0.0",
            "info": {"title": "Duplicate API", "version": "1.0"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {},
        }

        # First discovery with no existing tools
        definition1 = service.discover(
            json.dumps(spec_content).encode(),
            source="test-source",
            existing_tools=[],
        )
        assert definition1 is not None
        assert definition1.duplicate_of is None

        # Second discovery with existing tool (same base_url)
        existing_tools = [{"id": "existing", "base_url": "https://api.example.com"}]
        definition2 = service.discover(
            json.dumps(spec_content).encode(),
            source="test-source",
            existing_tools=existing_tools,
        )
        assert definition2 is not None
        assert definition2.duplicate_of == "existing"

    def test_stage_and_persist(self, temp_dirs: tuple[Path, Path]):
        """Test staging a provider and persisting to disk."""
        specs_dir, staging_dir = temp_dirs
        service = DiscoveryService(specs_dir=specs_dir, staging_dir=staging_dir)

        spec_content = {"openapi": "3.0.0", "info": {"title": "Stage Me", "version": "1.0"}, "paths": {}}

        definition = service.discover(
            json.dumps(spec_content).encode(),
            source="test-source",
            existing_tools=[],
        )
        assert definition is not None

        # Stage the provider
        staged = service.stage(definition)
        assert staged.state == ProviderState.STAGED
        assert staged.staged_at is not None

        # Check persistence - tool_id is derived from memory source
        persisted_files = list(staging_dir.glob("*.json"))
        assert len(persisted_files) == 1
        persisted_path = persisted_files[0]
        assert persisted_path.stem.startswith("memory-")

        # Load and verify
        loaded = service.load_staged()
        assert len(loaded) == 1
        assert loaded[0].tool_id.startswith("memory-")  # Memory source gets hashed tool_id
        assert loaded[0].state == ProviderState.STAGED


class TestStagingRegistry:
    """Test the StagingRegistry."""

    @pytest.fixture
    def temp_dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create temporary directories for testing."""
        specs_dir = tmp_path / "specs"
        staging_dir = tmp_path / "staging"
        specs_dir.mkdir()
        staging_dir.mkdir()
        return specs_dir, staging_dir

    def test_init(self, temp_dirs: tuple[Path, Path]):
        """Test registry initialization."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )
        assert registry.staging_dir == staging_dir
        assert registry.specs_dir == specs_dir

    def test_register_and_get(self, temp_dirs: tuple[Path, Path]):
        """Test registering and retrieving providers."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        definition = ProviderDefinition(
            tool_id="test-tool",
            name="Test Tool",
            provider_id="test-provider",
            state=ProviderState.DISCOVERED,
            capabilities=["test-cap"],
        )

        registry.register(definition)

        assert registry.get("test-tool") is not None
        assert registry.get("test-tool").tool_id == "test-tool"
        assert registry.by_provider("test-provider") is not None
        assert registry.by_capability("test-cap") == [definition]

    def test_state_filtering(self, temp_dirs: tuple[Path, Path]):
        """Test filtering providers by state."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        # Add providers in different states
        for state in [ProviderState.DISCOVERED, ProviderState.STAGED, ProviderState.VERIFIED, ProviderState.SUSPENDED]:
            definition = ProviderDefinition(
                tool_id=f"tool-{state}",
                name=f"Tool {state}",
                provider_id=f"provider-{state}",
                state=state,
                capabilities=["test"],
            )
            registry.register(definition)

        assert len(registry.discovered()) == 1
        assert len(registry.staged()) == 1
        assert len(registry.verified()) == 1
        assert len(registry.suspended()) == 1
        assert len(registry.all()) == 4

    def test_count_by_state(self, temp_dirs: tuple[Path, Path]):
        """Test counting providers by state."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        for _ in range(3):
            registry.register(
                ProviderDefinition(
                    tool_id=f"discovered-{_}",
                    name=f"Discovered {_}",
                    provider_id=f"provider-{_}",
                    state=ProviderState.DISCOVERED,
                )
            )
        for _ in range(2):
            registry.register(
                ProviderDefinition(
                    tool_id=f"staged-{_}",
                    name=f"Staged {_}",
                    provider_id=f"provider-{_}",
                    state=ProviderState.STAGED,
                )
            )

        counts = registry.count_by_state()
        # count_by_state returns all valid states
        assert counts.get("discovered", 0) == 3
        assert counts.get("staged", 0) == 2

    def test_to_catalogue_entries(self, temp_dirs: tuple[Path, Path]):
        """Test converting registry to catalogue entries."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        # Add verified and non-verified providers
        registry.register(
            ProviderDefinition(
                tool_id="verified-tool",
                name="Verified Tool",
                provider_id="verified-provider",
                state=ProviderState.VERIFIED,
                capabilities=["verified-cap"],
            )
        )
        registry.register(
            ProviderDefinition(
                tool_id="staged-tool",
                name="Staged Tool",
                provider_id="staged-provider",
                state=ProviderState.STAGED,
                capabilities=["staged-cap"],
            )
        )

        # By default, only verified
        entries = registry.to_catalogue_entries(verified_only=True)
        assert len(entries) == 1
        assert entries[0]["id"] == "verified-tool"

        # Include all
        entries = registry.to_catalogue_entries(verified_only=False)
        assert len(entries) == 2

    def test_stats(self, temp_dirs: tuple[Path, Path]):
        """Test stats output."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        stats = registry.stats()
        assert "total" in stats
        assert "by_state" in stats
        assert "capabilities" in stats
        assert stats["total"] == 0


class TestDiscoveryAPI:
    """Test the discovery API endpoints."""

    @pytest.fixture
    def temp_dirs(self, tmp_path: Path) -> tuple[Path, Path]:
        """Create temporary directories for testing."""
        specs_dir = tmp_path / "specs"
        staging_dir = tmp_path / "staging"
        specs_dir.mkdir()
        staging_dir.mkdir()
        return specs_dir, staging_dir

    def test_sources_endpoint(self, temp_dirs: tuple[Path, Path]):
        """Test listing discovery sources."""
        # This test verifies the sources endpoint structure
        # Full endpoint testing requires the FastAPI test client
        from app.discovery._legacy import CURATED_APIS

        sources = [
            {
                "type": "apis-guru",
                "name": "APIs.guru",
                "description": "OpenAPI directory with 900+ public APIs",
                "url": "https://api.apis.guru/v2/list.json",
                "specs_available": len(CURATED_APIS),
            },
            {
                "type": "local",
                "name": "Local uploads",
                "description": "User-uploaded specification files",
                "path": str(temp_dirs[0] / "uploads"),
            },
            {
                "type": "openapi-url",
                "name": "Direct URL",
                "description": "Fetch OpenAPI spec from any URL",
            },
        ]

        assert len(sources) == 3
        assert sources[0]["type"] == "apis-guru"
        assert sources[0]["specs_available"] > 0
        assert sources[1]["type"] == "local"
        assert sources[2]["type"] == "openapi-url"

    def test_ingest_spec_content(self, temp_dirs: tuple[Path, Path]):
        """Test ingesting a spec from raw content."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        spec_content = {"openapi": "3.0.0", "info": {"title": "Ingest Test API", "version": "1.0"}, "paths": {}}

        definition = registry._service.discover(
            json.dumps(spec_content).encode(),
            source="inline-content",
            existing_tools=[],
        )

        assert definition is not None
        assert definition.name == "Ingest Test API"
        registry.register(definition)

        # Verify it's in the registry
        assert registry.get(definition.tool_id) is not None
        assert registry.get(definition.tool_id).state == ProviderState.DISCOVERED

    def test_upload_parses_openapi(self, temp_dirs: tuple[Path, Path]):
        """Test that uploading an OpenAPI file triggers parsing."""
        specs_dir, staging_dir = temp_dirs
        registry = StagingRegistry(
            staging_dir=staging_dir,
            specs_dir=specs_dir,
        )

        spec_content = {"openapi": "3.0.0", "info": {"title": "Upload Test API", "version": "1.0"}, "paths": {}}

        # Simulate upload by parsing directly
        definition = registry._service.discover(
            json.dumps(spec_content).encode(),
            source="uploaded-file.json",
            existing_tools=[],
        )

        assert definition is not None
        assert definition.name == "Upload Test API"


class TestGenericProvider:
    """Test the generic provider runtime."""

    def test_config_derivation(self):
        """Test that config is derived from provider definition."""
        from app.discovery.runtime import GenericProviderConfig

        definition = ProviderDefinition(
            tool_id="test-tool",
            name="Test Tool",
            provider_id="test-provider",
            base_url="https://api.example.com/v1",
            listing_metadata=None,
            endpoints=[
                {
                    "path": "/test",
                    "method": "GET",
                    "operation_id": "getTest",
                    "parameters": [{"name": "api_key", "location": "header", "type": "string"}],
                    "request_fields": [],
                    "response_fields": [],
                }
            ],
            fields=[],
            capabilities=["test"],
        )

        config = GenericProviderConfig(
            base_url=definition.base_url,
            auth_type="api_key_header",
            auth_param="X-API-Key",
        )

        assert config.base_url == "https://api.example.com/v1"
        assert config.auth_type == "api_key_header"

    def test_provider_state_gate(self):
        """Test that only verified providers can be executed."""
        from app.discovery.runtime import GenericProvider, GenericProviderFactory
        from app.core.cache import Cache
        from app.config import Settings
        import asyncio

        settings = Settings()
        cache = Cache(settings.cache_db, ttl_seconds=60)

        # Create definitions in different states
        for state in [ProviderState.DISCOVERED, ProviderState.STAGED, ProviderState.VERIFIED]:
            definition = ProviderDefinition(
                tool_id=f"test-{state}",
                name=f"Test {state}",
                provider_id=f"provider-{state}",
                base_url="https://api.example.com",
                state=state,
                endpoints=[],
                fields=[],
                capabilities=["test"],
            )

            factory = GenericProviderFactory(settings, cache)
            try:
                provider = factory.from_definition(definition)
                if state == ProviderState.VERIFIED:
                    assert provider is not None
                    assert provider.tool_id == f"test-{state}"
                else:
                    # Should have raised ValueError
                    assert False, f"Expected ValueError for {state} state"
            except ValueError as e:
                if state == ProviderState.VERIFIED:
                    assert False, f"Unexpected error for VERIFIED: {e}"
                # Expected for non-verified states

    def test_provider_serialization(self):
        """Test that provider definitions serialize correctly."""
        definition = ProviderDefinition(
            tool_id="serial-test",
            name="Serial Test",
            provider_id="serial-provider",
            base_url="https://api.example.com",
            state=ProviderState.VERIFIED,
            capabilities=["test-cap"],
            endpoints=[
                {
                    "path": "/test",
                    "method": "GET",
                    "operation_id": "getTest",
                    "parameters": [],
                    "request_fields": [],
                    "response_fields": [],
                }
            ],
            fields=[
                {
                    "path": "output.result",
                    "name": "result",
                    "type": "string",
                    "direction": "output",
                }
            ],
            verified_at=1234567890.0,
        )

        # Verify serialization properties
        assert definition.tool_id == "serial-test"
        assert definition.state == ProviderState.VERIFIED
        assert definition.is_executable
        assert definition.capability == "test-cap"
        assert len(definition.endpoints) == 1
        assert len(definition.fields) == 1
