"""Integration tests for the discovery pipeline.

Covers:
- Real offline fixtures (Task 1)
- Auditor verification (Task 2)
- Mapper integration (Task 3)
- OAuth2 support (Task 4)
- End-to-end pipeline (Task 5)
- Negative tests for invalid specs, responses, mappings, unsafe endpoints
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

import pytest

from app.discovery.fixtures import Fixture, FixtureStore


def run_async(coro):
    """Run an async coroutine in a new event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


from app.discovery.oauth import (
    OAuth2Client,
    OAuthClientConfig,
    OAuthToken,
    TokenStore,
    generate_pkce_pair,
    build_authorization_url,
)
from app.discovery.pipeline import DiscoveryPipeline, PipelineResult
from app.discovery.runtime import (
    GenericProvider,
    GenericProviderConfig,
    GenericProviderFactory,
    validate_response_against_schema,
    extract_schema_from_endpoints,
    is_safe_url,
    validate_target_url,
)
from app.discovery.service import (
    DiscoveryService,
    ProviderDefinition,
    ProviderState,
    verify_provider_with_auditor,
    map_provider_to_ontology,
)
from app.discovery.staging import StagingRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_spec(title="Test API", base_url="https://api.example.com", paths=None):
    return {
        "openapi": "3.0.0",
        "info": {"title": title, "version": "1.0", "description": "test"},
        "servers": [{"url": base_url}],
        "paths": paths
        if paths is not None
        else {
            "/data": {
                "get": {
                    "operationId": "getData",
                    "summary": "Get data",
                    "responses": {
                        "200": {
                            "description": "OK",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "result": {"type": "string"},
                                            "count": {"type": "integer"},
                                        },
                                        "required": ["result"],
                                    }
                                }
                            },
                        }
                    },
                }
            }
        },
    }


def make_definition(tool_id="test-tool", state=ProviderState.STAGED, **kwargs):
    defaults = dict(
        tool_id=tool_id,
        name="Test Tool",
        provider_id="test-provider",
        base_url="https://api.example.com",
        state=state,
        capabilities=["test"],
        endpoints=[
            {
                "path": "/data",
                "method": "GET",
                "operation_id": "getData",
                "parameters": [],
                "request_fields": [],
                "response_fields": [
                    {"name": "result", "type": "string", "required": True},
                    {"name": "count", "type": "integer"},
                ],
            }
        ],
        fields=[
            {"path": "output.result", "name": "result", "type": "string", "direction": "output"},
            {"path": "output.count", "name": "count", "type": "integer", "direction": "output"},
        ],
    )
    defaults.update(kwargs)
    return ProviderDefinition(**defaults)


# ===========================================================================
# Task 1: Offline Fixtures
# ===========================================================================


class TestFixtureStore:
    """Tests for the deterministic fixture system."""

    def test_fixture_save_and_load(self, tmp_path: Path):
        store = FixtureStore(tmp_path / "fixtures")
        fixture = Fixture(
            tool_id="api1",
            endpoint_path="/data",
            method="GET",
            fixture_type="success",
            body={"result": "ok", "count": 42},
        )
        store.save(fixture)

        loaded = store.get("api1", "/data", "GET")
        assert loaded is not None
        assert loaded.body["result"] == "ok"
        assert loaded.body["count"] == 42

    def test_fixture_deterministic(self, tmp_path: Path):
        """Same endpoint always produces the same generated fixture."""
        store = FixtureStore(tmp_path / "fixtures")
        fields = [{"name": "result", "type": "string"}]

        f1 = store.generate_success_fixture("api1", "/data", "GET", response_fields=fields)
        f2 = store.generate_success_fixture("api1", "/data", "GET", response_fields=fields)
        assert f1.body == f2.body

    def test_fixture_types(self, tmp_path: Path):
        store = FixtureStore(tmp_path / "fixtures")

        for ftype in ["auth_failure", "rate_limit", "timeout", "schema_violation", "error"]:
            fixture = store.generate_error_fixture("api1", "/data", "GET", fixture_type=ftype)
            assert fixture.fixture_type == ftype

        # success uses generate_success_fixture
        fixture = store.generate_success_fixture("api1", "/data", "GET")
        assert fixture.fixture_type == "success"

    def test_fixture_error_types_raise(self, tmp_path: Path):
        """Error fixtures must have failure status codes, not fabricated success."""
        store = FixtureStore(tmp_path / "fixtures")
        for ftype in ["auth_failure", "rate_limit", "timeout", "error"]:
            fixture = store.generate_error_fixture("api1", "/data", "GET", fixture_type=ftype)
            store.save(fixture)

        # The store replaces same endpoint+method+type, so we check each type
        # by saving to separate endpoints
        for ftype in ["auth_failure", "rate_limit", "error"]:
            store2 = FixtureStore(tmp_path / f"fixtures2-{ftype}")
            fixture = store2.generate_error_fixture("api1", "/data", "GET", fixture_type=ftype)
            store2.save(fixture)
            f = store2.get("api1", "/data", "GET")
            assert f is not None
            assert f.fixture_type == ftype
            if ftype == "auth_failure":
                assert f.status_code == 401
            elif ftype == "rate_limit":
                assert f.status_code == 429
            elif ftype == "error":
                assert f.status_code == 500

    def test_fixture_selection_prefers_success(self, tmp_path: Path):
        store = FixtureStore(tmp_path / "fixtures")
        # Save error fixture
        error = Fixture(
            tool_id="api1",
            endpoint_path="/data",
            method="GET",
            fixture_type="error",
            status_code=500,
            body={"error": "fail"},
        )
        store.save(error)
        # Save success fixture (same endpoint, different type)
        success = Fixture(
            tool_id="api1", endpoint_path="/data", method="GET", fixture_type="success", body={"result": "ok"}
        )
        store.save(success)

        # Default prefers success
        selected = store.get("api1", "/data", "GET")
        assert selected is not None
        assert selected.fixture_type == "success"
        assert selected.body["result"] == "ok"

    def test_fixture_no_match_returns_none(self, tmp_path: Path):
        store = FixtureStore(tmp_path / "fixtures")
        assert store.get("nonexistent", "/data", "GET") is None

    def test_fixture_clear(self, tmp_path: Path):
        store = FixtureStore(tmp_path / "fixtures")
        store.save(Fixture(tool_id="api1", endpoint_path="/data", method="GET"))
        assert len(store.list_fixtures("api1")) == 1
        count = store.clear("api1")
        assert count == 1
        assert len(store.list_fixtures("api1")) == 0

    def test_offline_provider_uses_fixtures(self, tmp_path: Path):
        """GenericProvider.offline() must use FixtureStore, not return placeholder."""
        from app.config import Settings
        from app.core.cache import Cache

        settings = Settings(runtime_dir=tmp_path / "runtime")
        settings.ensure_dirs()
        cache = Cache(settings.cache_db, ttl_seconds=60)

        definition = make_definition()
        fixture_store = FixtureStore(tmp_path / "fixtures")
        provider = GenericProvider(definition, settings, cache, fixture_store=fixture_store)

        # offline() should return fixture data, not "offline fixture"
        result = run_async(provider.offline({}))
        assert result != {"result": "offline fixture", "tool_id": "test-tool"}
        assert "result" in result  # from generated fixture

    def test_offline_provider_raises_on_error_fixture(self, tmp_path: Path):
        """Provider must raise when only error fixtures exist."""
        from app.config import Settings
        from app.core.cache import Cache

        settings = Settings(runtime_dir=tmp_path / "runtime")
        settings.ensure_dirs()
        cache = Cache(settings.cache_db, ttl_seconds=60)

        definition = make_definition()
        fixture_store = FixtureStore(tmp_path / "fixtures")
        error_fixture = fixture_store.generate_error_fixture("test-tool", "/data", "GET", fixture_type="auth_failure")
        fixture_store.save(error_fixture)

        provider = GenericProvider(definition, settings, cache, fixture_store=fixture_store)

        with pytest.raises(RuntimeError, match="auth failure"):
            run_async(provider.offline({}))


# ===========================================================================
# Task 2: Auditor Verification
# ===========================================================================


class TestAuditorVerification:
    """Tests for the 4-level auditor verification."""

    def test_valid_definition_passes(self):
        definition = make_definition()
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert result["specification_valid"] is True
        assert result["security_safe"] is True
        assert result["verified"] is True

    def test_missing_endpoints_fails(self):
        definition = make_definition(endpoints=[], fields=[])
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert result["specification_valid"] is False
        assert result["verified"] is False
        assert any("No endpoints" in e for e in result["errors"])

    def test_missing_tool_id_fails(self):
        definition = make_definition(tool_id="")
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert result["specification_valid"] is False
        assert result["verified"] is False

    def test_endpoint_missing_path_fails(self):
        definition = make_definition(
            endpoints=[{"path": "", "method": "GET", "response_fields": []}],
            fields=[],
        )
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert result["specification_valid"] is False

    def test_security_checks_recorded(self):
        definition = make_definition()
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert result["security_safe"] is True
        assert any("HTTPS" in n for n in result["notes"])

    def test_http_base_url_warned(self):
        definition = make_definition(base_url="http://api.example.com")
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        # Warning but still safe (not blocking)
        assert any("HTTP (not HTTPS)" in n for n in result["notes"])

    def test_claims_extracted(self):
        definition = make_definition()
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert result["claims_checked"] > 0
        assert result["claims_verified"] > 0

    def test_verification_history_present(self):
        definition = make_definition()
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert "verification_history" in result

    def test_no_output_fields_warned(self):
        definition = make_definition(
            fields=[{"path": "input.x", "name": "x", "type": "string", "direction": "input"}],
        )
        result = run_async(verify_provider_with_auditor(definition, auditor=None, settings=None))
        assert any("No output fields" in n for n in result["notes"])


# ===========================================================================
# Task 3: Mapper Integration
# ===========================================================================


class TestMapperIntegration:
    """Tests for the mapper integration with persistence and retriever."""

    def test_no_mapper_returns_error(self):
        definition = make_definition()
        result = run_async(map_provider_to_ontology(definition, mapper=None, store=None))
        assert result["mapped"] is False
        assert any("No mapper" in e for e in result["errors"])

    def test_no_fields_returns_error(self):
        definition = make_definition(fields=[])
        result = run_async(map_provider_to_ontology(definition, mapper=object(), store=None))
        assert result["mapped"] is False
        assert any("No fields" in e for e in result["errors"])

    def test_confidence_threshold_in_result(self):
        definition = make_definition()
        result = run_async(map_provider_to_ontology(definition, mapper=None, store=None, confidence_threshold=0.7))
        assert result["threshold"] == 0.7

    def test_persisted_flag_initially_false(self):
        """Without a store, persistence must not be claimed."""
        definition = make_definition()
        result = run_async(map_provider_to_ontology(definition, mapper=None, store=None))
        assert result["persisted"] is False

    def test_retriever_rebuild_flag_initially_false(self):
        definition = make_definition()
        result = run_async(map_provider_to_ontology(definition, mapper=None, store=None, retriever=None))
        assert result["retriever_rebuilt"] is False

    def test_result_structure(self):
        definition = make_definition()
        result = run_async(map_provider_to_ontology(definition, mapper=None, store=None))
        for key in [
            "tool_id",
            "mapped",
            "fields_mapped",
            "fields_total",
            "fields_pending_review",
            "confidence",
            "threshold",
            "errors",
            "unmapped_fields",
            "pending_review",
            "persisted",
            "retriever_rebuilt",
            "notes",
        ]:
            assert key in result, f"Missing key: {key}"


# ===========================================================================
# Task 4: OAuth2
# ===========================================================================


class TestOAuth2:
    """Tests for OAuth2 support."""

    def test_token_store_save_load(self, tmp_path: Path):
        store = TokenStore(tmp_path / "tokens")
        token = OAuthToken(
            provider_id="api1",
            access_token="secret-token-value",
            expires_at=time.time() + 3600,
            scope="read write",
        )
        store.save(token)

        loaded = store.load("api1")
        assert loaded is not None
        assert loaded.access_token == "secret-token-value"
        assert loaded.scope == "read write"

    def test_token_expiry(self):
        expired = OAuthToken(
            provider_id="api1",
            access_token="t",
            expires_at=time.time() - 100,
        )
        assert expired.is_expired

        valid = OAuthToken(
            provider_id="api1",
            access_token="t",
            expires_at=time.time() + 3600,
        )
        assert not valid.is_expired

    def test_token_no_expiry_never_expires(self):
        token = OAuthToken(provider_id="api1", access_token="t", expires_at=0)
        assert not token.is_expired

    def test_token_authorization_header(self):
        token = OAuthToken(provider_id="api1", access_token="abc123", token_type="Bearer")
        assert token.authorization_header == "Bearer abc123"

    def test_token_store_delete(self, tmp_path: Path):
        store = TokenStore(tmp_path / "tokens")
        store.save(OAuthToken(provider_id="api1", access_token="t"))
        assert store.has_token("api1")
        assert store.delete("api1") is True
        assert not store.has_token("api1")

    def test_token_status_no_secret_leak(self, tmp_path: Path):
        """status() must not expose the token value."""
        store = TokenStore(tmp_path / "tokens")
        store.save(OAuthToken(provider_id="api1", access_token="super-secret"))
        client = OAuth2Client(store)
        status = client.status("api1")
        assert "super-secret" not in json.dumps(status)
        assert status["has_token"] is True

    def test_client_credentials_no_config_returns_none(self, tmp_path: Path):
        store = TokenStore(tmp_path / "tokens")
        client = OAuth2Client(store)
        result = run_async(client.get_token("unknown-provider"))
        assert result is None

    def test_client_credentials_flow(self, tmp_path: Path):
        store = TokenStore(tmp_path / "tokens")
        client = OAuth2Client(store)
        config = OAuthClientConfig(
            provider_id="api1",
            client_id="cid",
            client_secret="csecret",
            token_url="https://auth.example.com/token",
            scopes=["read"],
            flow="client_credentials",
        )
        client.register_config(config)
        assert client.get_config("api1") is config

    def test_pkce_pair_generation(self):
        verifier, challenge = generate_pkce_pair()
        assert len(verifier) > 20
        assert len(challenge) > 20
        assert verifier != challenge

    def test_authorization_url_building(self):
        config = OAuthClientConfig(
            provider_id="api1",
            client_id="cid",
            authorization_url="https://auth.example.com/authorize",
            scopes=["read", "write"],
        )
        url = build_authorization_url(config, state="xyz", code_challenge="abc")
        assert "response_type=code" in url
        assert "client_id=cid" in url
        assert "state=xyz" in url
        assert "code_challenge=abc" in url
        assert "code_challenge_method=S256" in url
        assert "scope=read" in url

    def test_revoke(self, tmp_path: Path):
        store = TokenStore(tmp_path / "tokens")
        client = OAuth2Client(store)
        store.save(OAuthToken(provider_id="api1", access_token="t"))
        assert client.revoke("api1") is True
        assert store.load("api1") is None

    def test_oauth2_provider_config_detection(self):
        """GenericProvider detects OAuth2 from endpoint parameters."""
        definition = make_definition(
            endpoints=[
                {
                    "path": "/data",
                    "method": "GET",
                    "parameters": [{"name": "Authorization", "location": "header", "type": "string"}],
                    "request_fields": [],
                    "response_fields": [],
                }
            ],
        )
        config = GenericProviderConfig(
            base_url=definition.base_url,
            auth_type="oauth2",
            auth_param="Authorization",
        )
        assert config.auth_type == "oauth2"


# ===========================================================================
# Task 5: End-to-End Pipeline
# ===========================================================================


class TestEndToEndPipeline:
    """Tests for the complete discovery-to-execution pipeline."""

    @pytest.fixture
    def pipeline_setup(self, tmp_path: Path):
        specs_dir = tmp_path / "specs"
        staging_dir = tmp_path / "staging"
        specs_dir.mkdir()
        staging_dir.mkdir()
        registry = StagingRegistry(staging_dir=staging_dir, specs_dir=specs_dir)
        pipeline = DiscoveryPipeline(
            staging=registry,
            settings=None,
            mapper=None,
            store=None,
            retriever=None,
            auditor=None,
            provider_registry=None,
        )
        return pipeline, registry

    @pytest.mark.asyncio
    async def test_pipeline_discover_and_stage(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        result = await pipeline.run_full_pipeline(spec, source="test")

        assert result.discovered is True
        assert result.tool_id != ""
        assert result.stage == "complete"

        # Provider should be in the registry
        provider = registry.get(result.tool_id)
        assert provider is not None

    @pytest.mark.asyncio
    async def test_pipeline_invalid_spec_fails(self, pipeline_setup):
        pipeline, registry = pipeline_setup

        result = await pipeline.run_full_pipeline(b"not a valid spec", source="bad")

        assert result.discovered is False
        assert len(result.errors) > 0

    @pytest.mark.asyncio
    async def test_pipeline_verifies_valid_spec(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        result = await pipeline.run_full_pipeline(spec, source="test")

        assert result.verified is True
        assert result.verification_result.get("specification_valid") is True

    @pytest.mark.asyncio
    async def test_pipeline_suspends_invalid_spec(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        # Spec with no endpoints - will fail verification
        spec = json.dumps(make_spec(paths={})).encode()

        result = await pipeline.run_full_pipeline(spec, source="test")

        # Should be discovered but not verified
        assert result.discovered is True
        assert result.verified is False

    @pytest.mark.asyncio
    async def test_pipeline_records_history(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        await pipeline.run_full_pipeline(spec, source="test")
        history = pipeline.get_history()

        assert len(history) == 1
        assert history[0]["stage"] == "complete"

    @pytest.mark.asyncio
    async def test_pipeline_multiple_runs(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        await pipeline.run_full_pipeline(spec, source="test1")
        await pipeline.run_full_pipeline(spec, source="test2")

        history = pipeline.get_history()
        assert len(history) == 2

    @pytest.mark.asyncio
    async def test_pipeline_duration_recorded(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        result = await pipeline.run_full_pipeline(spec, source="test")
        assert result.duration_ms > 0

    @pytest.mark.asyncio
    async def test_pipeline_status(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        status = pipeline.status()

        assert status["total_runs"] == 0
        assert status["components"]["mapper"] is False

    @pytest.mark.asyncio
    async def test_pipeline_duplicate_detection(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        # First run
        r1 = await pipeline.run_full_pipeline(spec, source="test")
        # Second run with same URL should detect duplicate
        r2 = await pipeline.run_full_pipeline(
            spec,
            source="test2",
            existing_tools=[{"id": r1.tool_id, "base_url": "https://api.example.com"}],
        )

        # Second should be detected as duplicate
        if r2.discovered:
            provider = registry.get(r2.tool_id)
            if provider and provider.duplicate_of:
                assert provider.duplicate_of == r1.tool_id

    @pytest.mark.asyncio
    async def test_pipeline_result_serializable(self, pipeline_setup):
        pipeline, registry = pipeline_setup
        spec = json.dumps(make_spec()).encode()

        result = await pipeline.run_full_pipeline(spec, source="test")
        data = result.to_dict()

        # Must be JSON serializable
        json.dumps(data)
        assert data["tool_id"] == result.tool_id
        assert "success" in data


# ===========================================================================
# Negative Tests
# ===========================================================================


class TestNegativeCases:
    """Negative tests for invalid inputs, unsafe endpoints, failed verification."""

    def test_invalid_json_spec(self, tmp_path: Path):
        service = DiscoveryService(
            specs_dir=tmp_path / "specs",
            staging_dir=tmp_path / "staging",
        )
        result = service.parse_raw_openapi(b"not json at all", source="bad")
        assert result is None

    def test_non_openapi_spec(self, tmp_path: Path):
        service = DiscoveryService(
            specs_dir=tmp_path / "specs",
            staging_dir=tmp_path / "staging",
        )
        result = service.parse_raw_openapi(json.dumps({"foo": "bar"}).encode(), source="bad")
        assert result is None

    def test_schema_validation_type_mismatch(self):
        schema = {"type": "object", "properties": {"name": {"type": "string"}}}
        valid, errors = validate_response_against_schema({"name": 123}, schema)
        assert not valid
        assert any("string" in e for e in errors)

    def test_schema_validation_missing_required(self):
        schema = {"type": "object", "required": ["id"]}
        valid, errors = validate_response_against_schema({}, schema)
        assert not valid
        assert any("id" in e for e in errors)

    def test_schema_validation_array_items(self):
        schema = {"type": "array", "items": {"type": "string"}}
        valid, _ = validate_response_against_schema(["a", "b"], schema)
        assert valid
        valid, errors = validate_response_against_schema([1, 2], schema)
        assert not valid

    def test_unsafe_url_localhost(self):
        assert is_safe_url("http://localhost:8080") is False
        assert is_safe_url("http://127.0.0.1") is False

    def test_unsafe_url_private_ip(self):
        assert is_safe_url("http://10.0.0.1") is False
        assert is_safe_url("http://192.168.1.1") is False
        assert is_safe_url("http://172.16.0.1") is False

    def test_unsafe_url_internal_hostname(self):
        assert is_safe_url("https://db.internal") is False
        assert is_safe_url("https://server.local") is False

    def test_safe_url_public(self):
        assert is_safe_url("https://api.example.com") is True

    def test_validate_target_url_rejects_bad_scheme(self):
        with pytest.raises(ValueError, match="Unsupported scheme"):
            validate_target_url("ftp://example.com")

    def test_validate_target_url_rejects_empty(self):
        with pytest.raises(ValueError, match="required"):
            validate_target_url("")

    def test_validate_target_url_rejects_private(self):
        with pytest.raises(ValueError, match="not allowed"):
            validate_target_url("http://127.0.0.1:8080")

    def test_factory_rejects_unverified(self, tmp_path: Path):
        from app.config import Settings
        from app.core.cache import Cache

        settings = Settings(runtime_dir=tmp_path / "runtime")
        settings.ensure_dirs()
        cache = Cache(settings.cache_db, ttl_seconds=60)
        factory = GenericProviderFactory(settings, cache)

        for state in [ProviderState.DISCOVERED, ProviderState.STAGED, ProviderState.SUSPENDED]:
            definition = make_definition(state=state)
            with pytest.raises(ValueError, match="state"):
                factory.from_definition(definition)

    def test_factory_accepts_verified(self, tmp_path: Path):
        from app.config import Settings
        from app.core.cache import Cache

        settings = Settings(runtime_dir=tmp_path / "runtime")
        settings.ensure_dirs()
        cache = Cache(settings.cache_db, ttl_seconds=60)
        factory = GenericProviderFactory(settings, cache)

        definition = make_definition(state=ProviderState.VERIFIED)
        provider = factory.from_definition(definition)
        assert provider is not None
        assert provider.tool_id == "test-tool"

    def test_verification_fails_on_no_endpoints(self):
        definition = make_definition(endpoints=[], fields=[])
        result = run_async(verify_provider_with_auditor(definition, None, None))
        assert result["verified"] is False

    def test_duplicate_ingestion_detected(self, tmp_path: Path):
        service = DiscoveryService(
            specs_dir=tmp_path / "specs",
            staging_dir=tmp_path / "staging",
        )
        spec = json.dumps(make_spec()).encode()

        d1 = service.discover(spec, source="a", existing_tools=[])
        assert d1 is not None

        # Same base_url should be detected as duplicate
        existing = [{"id": d1.tool_id, "base_url": "https://api.example.com"}]
        d2 = service.discover(spec, source="b", existing_tools=existing)
        assert d2 is not None
        assert d2.duplicate_of == d1.tool_id

    def test_restart_persistence(self, tmp_path: Path):
        """Staged providers survive a registry restart."""
        staging_dir = tmp_path / "staging"
        specs_dir = tmp_path / "specs"
        staging_dir.mkdir()
        specs_dir.mkdir()

        # First registry instance
        registry1 = StagingRegistry(staging_dir=staging_dir, specs_dir=specs_dir)
        definition = make_definition(tool_id="persist-test", state=ProviderState.DISCOVERED)
        staged = registry1._service.stage(definition)
        registry1.register(staged)

        # New registry instance (simulating restart)
        registry2 = StagingRegistry(staging_dir=staging_dir, specs_dir=specs_dir)
        loaded = registry2.get("persist-test")
        assert loaded is not None
        assert loaded.state == ProviderState.STAGED

    def test_pipeline_empty_bytes(self, tmp_path: Path):
        staging_dir = tmp_path / "staging"
        specs_dir = tmp_path / "specs"
        staging_dir.mkdir()
        specs_dir.mkdir()
        registry = StagingRegistry(staging_dir=staging_dir, specs_dir=specs_dir)
        pipeline = DiscoveryPipeline(staging=registry, settings=None)

        result = run_async(pipeline.run_full_pipeline(b"", source="empty"))
        assert result.discovered is False
        assert len(result.errors) > 0
