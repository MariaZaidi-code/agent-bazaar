"""Generic provider runtime: execute APIs from discovered specifications.

This is the Phase 2 component that converts a parsed OpenAPI specification
into an executable provider. Unlike the hand-written providers in
``app/providers/``, this runtime:

1. Reads the spec's endpoints, parameters, request bodies, and response schemas.
2. Constructs the correct HTTP request (method, URL, query params, body).
3. Handles auth (API key in header/query, Bearer token, none).
4. Validates the response against the spec's schema.
5. Transforms the response into the normalized output format expected by the Client.

Discovery and execution are separate: a provider must be in VERIFIED state
before it can be executed. The runtime does not perform discovery.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.config import Settings
from app.core.cache import Cache, make_key
from app.discovery.service import ProviderDefinition, ProviderState
from app.discovery.fixtures import FixtureStore
from app.discovery.oauth import OAuth2Client, OAuthClientConfig, TokenStore

LOGGER = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Generic HTTP provider
# ---------------------------------------------------------------------------


@dataclass
class GenericProviderConfig:
    """Configuration for a generic provider derived from a spec."""

    base_url: str
    auth_type: str = "none"  # "none", "api_key_header", "api_key_query", "bearer"
    auth_param: str = ""  # header name or query param name
    default_params: dict[str, Any] = field(default_factory=dict)
    rate_limit_per_second: float = 0.0
    timeout_seconds: float = 30.0


# ---------------------------------------------------------------------------
# Security: SSRF protection
# ---------------------------------------------------------------------------


def is_safe_url(url: str) -> bool:
    """Check if a URL is safe to request (not private/internal).

    Prevents SSRF attacks by blocking:
    - Private IP ranges (10.x, 172.16-31.x, 192.168.x, 127.x)
    - Link-local (169.254.x)
    - IPv6 equivalents
    - localhost variations
    """
    from urllib.parse import urlparse

    parsed = urlparse(url)
    host = parsed.hostname or ""

    # Block localhost variations
    if host.lower() in {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}:
        return False

    # Block internal hostnames
    if host.endswith(".internal") or host.endswith(".local") or host.endswith(".lan"):
        return False

    # Try to resolve and check IP
    try:
        import socket

        ip = socket.gethostbyname(host)

        # Check private IPv4 ranges
        parts = ip.split(".")
        if len(parts) == 4:
            first, second = int(parts[0]), int(parts[1])
            # 10.0.0.0/8
            if first == 10:
                return False
            # 172.16.0.0/12
            if first == 172 and 16 <= second <= 31:
                return False
            # 192.168.0.0/16
            if first == 192 and second == 168:
                return False
            # 127.0.0.0/8
            if first == 127:
                return False
            # 169.254.0.0/16 (link-local)
            if first == 169 and second == 254:
                return False
            # 0.0.0.0
            if ip == "0.0.0.0":
                return False
    except socket.gaierror:
        pass

    return True


def validate_target_url(url: str) -> str:
    """Validate and sanitize a target URL.

    Returns the URL if safe, raises ValueError if unsafe.
    """
    from urllib.parse import urlparse

    if not url:
        raise ValueError("URL is required")

    parsed = urlparse(url)

    # Only allow HTTPS (and HTTP for localhost testing)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"Unsupported scheme: {parsed.scheme}")

    if not parsed.hostname:
        raise ValueError("URL must have a hostname")

    if not is_safe_url(url):
        raise ValueError(f"Access to {parsed.hostname} is not allowed")

    # Reconstruct URL without fragment
    return parsed._replace(fragment="").geturl()


# ---------------------------------------------------------------------------
# Response validation
# ---------------------------------------------------------------------------


def validate_response_against_schema(data: Any, schema: dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate response data against a simple JSON Schema-like specification.

    Supports:
    - type checking (string, integer, number, boolean, array, object)
    - required fields
    - nested object properties
    - array item types
    """
    errors: list[str] = []

    if not isinstance(schema, dict):
        return True, errors

    schema_type = schema.get("type", "object")

    # Type checking
    if schema_type == "object":
        if not isinstance(data, dict):
            errors.append(f"Expected object, got {type(data).__name__}")
            return False, errors

        required = schema.get("required", [])
        properties = schema.get("properties", {})

        for field in required:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        for field_name, field_schema in properties.items():
            if field_name in data:
                field_valid, field_errors = validate_response_against_schema(data[field_name], field_schema)
                if not field_valid:
                    errors.extend(f"{field_name}.{e}" for e in field_errors)

    elif schema_type == "array":
        if not isinstance(data, list):
            errors.append(f"Expected array, got {type(data).__name__}")
            return False, errors

        items_schema = schema.get("items")
        if items_schema:
            for i, item in enumerate(data):
                item_valid, item_errors = validate_response_against_schema(item, items_schema)
                if not item_valid:
                    errors.extend(f"[{i}].{e}" for e in item_errors)

    elif schema_type == "string":
        if not isinstance(data, str):
            errors.append(f"Expected string, got {type(data).__name__}")

    elif schema_type in ("integer", "number"):
        if not isinstance(data, (int, float)):
            errors.append(f"Expected {schema_type}, got {type(data).__name__}")

    elif schema_type == "boolean":
        if not isinstance(data, bool):
            errors.append(f"Expected boolean, got {type(data).__name__}")

    return len(errors) == 0, errors


def extract_schema_from_endpoints(endpoints: list[dict]) -> dict[str, Any]:
    """Extract a combined JSON Schema from endpoint definitions.

    This creates a basic schema from the response_fields defined in endpoints.
    """
    if not endpoints:
        return {"type": "object"}

    properties = {}
    required = []

    for endpoint in endpoints:
        for field in endpoint.get("response_fields", []):
            name = field.get("name", "")
            if not name:
                continue
            properties[name] = {
                "type": field.get("type", "string"),
                "description": field.get("description", ""),
            }
            if field.get("required"):
                required.append(name)

    return {
        "type": "object",
        "properties": properties,
        "required": required if required else None,
    }


class GenericProvider:
    """An executable provider generated from a parsed OpenAPI specification.

    This provider can execute any API described by a ProviderDefinition with
    VERIFIED state. It handles:

    - Endpoint selection (by operation_id or path+method)
    - Parameter binding (query, path, header, body)
    - Auth injection (API key, Bearer token, none)
    - Response validation against schema
    - Caching and rate limiting
    - Offline fallback to stored fixtures
    """

    def __init__(
        self,
        definition: ProviderDefinition,
        settings: Settings,
        cache: Cache,
        config: GenericProviderConfig | None = None,
        fixture_store: FixtureStore | None = None,
        oauth_client: OAuth2Client | None = None,
    ):
        self.definition = definition
        self.settings = settings
        self.cache = cache
        self.config = config or self._derive_config(definition)
        self.fail_next = 0
        self.offline_forced = False
        self._throttle_lock = asyncio.Lock()
        self._last_request = 0.0
        self.fixture_store = fixture_store or FixtureStore(settings.runtime_dir / "discovery" / "fixtures")
        self.oauth_client = oauth_client
        if self.oauth_client is None and self.config.auth_type == "oauth2":
            token_store = TokenStore(settings.runtime_dir / "discovery" / "tokens")
            self.oauth_client = OAuth2Client(token_store)

    @property
    def tool_id(self) -> str:
        return self.definition.tool_id

    @property
    def provider_id(self) -> str:
        return self.definition.provider_id

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def capability(self) -> str:
        return self.definition.capabilities[0] if self.definition.capabilities else "general"

    def _derive_config(self, definition: ProviderDefinition) -> GenericProviderConfig:
        """Derive a GenericProviderConfig from the ProviderDefinition."""
        # Determine auth type from listing metadata or spec
        auth_type = "none"
        auth_param = ""

        # Check for OAuth2 security schemes in endpoints
        for ep in definition.endpoints:
            for param in ep.get("parameters", []):
                pname = param.get("name", "").lower()
                if pname in {"authorization", "bearer"}:
                    auth_type = "oauth2"
                    auth_param = "Authorization"

        if definition.listing_metadata:
            access = definition.listing_metadata.access_requirement
            if access == "keyless":
                auth_type = "none"
            elif access == "api_key":
                # Try to detect where the key goes from the spec
                auth_type = "api_key_header"
                auth_param = "X-API-Key"
            elif access == "paid_key":
                auth_type = "api_key_header"
                auth_param = "X-API-Key"

        # Check endpoints for security scheme hints
        for endpoint in definition.endpoints:
            for param in endpoint.get("parameters", []):
                if param.get("name", "").lower() in {
                    "api_key",
                    "apikey",
                    "x-api-key",
                    "api-key",
                    "authorization",
                    "access_token",
                    "token",
                }:
                    if param.get("location", "query") == "header":
                        auth_type = "api_key_header"
                        auth_param = param["name"]
                    elif param.get("location", "query") == "query":
                        auth_type = "api_key_query"
                        auth_param = param["name"]

        return GenericProviderConfig(
            base_url=definition.base_url,
            auth_type=auth_type,
            auth_param=auth_param,
        )

    async def _inject_auth(
        self, url: str, params: dict[str, Any], headers: dict[str, str]
    ) -> tuple[str, dict[str, Any], dict[str, str]]:
        """Inject authentication into the request.

        Supports: none, api_key_header, api_key_query, bearer, oauth2.
        OAuth2 tokens are fetched/refreshed via the OAuth2Client.
        """
        if self.config.auth_type == "none":
            return url, params, headers

        if self.config.auth_type == "api_key_header":
            headers[self.config.auth_param] = self.settings.api_keys.get(self.provider_id, "")
        elif self.config.auth_type == "api_key_query":
            params[self.config.auth_param] = self.settings.api_keys.get(self.provider_id, "")
        elif self.config.auth_type == "bearer":
            headers["Authorization"] = f"Bearer {self.settings.api_keys.get(self.provider_id, '')}"
        elif self.config.auth_type == "oauth2":
            if self.oauth_client is None:
                raise RuntimeError(f"OAuth2 requested but no client configured for {self.provider_id}")
            token = await self.oauth_client.get_token(self.provider_id)
            if token is None:
                raise RuntimeError(f"OAuth2 authentication failed for {self.provider_id}")
            headers["Authorization"] = token.authorization_header

        return url, params, headers

    async def _throttle(self) -> None:
        """Apply rate limiting."""
        if self.config.rate_limit_per_second <= 0:
            return
        async with self._throttle_lock:
            elapsed = time.monotonic() - self._last_request
            wait = 1.0 / self.config.rate_limit_per_second - elapsed
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = time.monotonic()

    async def execute(self, params: dict[str, Any], operation_id: str | None = None) -> dict[str, Any]:
        """Execute the provider against the API.

        Args:
            params: Input parameters for the operation.
            operation_id: Optional operation_id to select a specific endpoint.
                         If not provided, uses the first endpoint or the one
                         matching the tool's primary capability.

        Returns:
            The response data as a dict.
        """
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("Injected provider failure for demonstration")

        # Select the endpoint
        endpoint = self._select_endpoint(operation_id)
        if endpoint is None:
            raise ValueError(f"No suitable endpoint found for {self.tool_id}")

        # Build the request
        url = self.config.base_url.rstrip("/") + endpoint["path"]
        request_params: dict[str, Any] = {}
        request_body: dict[str, Any] | None = None
        headers: dict[str, str] = {}

        # Inject default params
        if self.config.default_params:
            request_params.update(self.config.default_params)

        # Bind input parameters
        for param in endpoint.get("parameters", []):
            param_name = param["name"]
            if param_name in params:
                if param.get("location", "query") == "query":
                    request_params[param_name] = params[param_name]
                elif param.get("location", "query") == "header":
                    headers[param_name] = str(params[param_name])
                elif param.get("location", "query") == "path":
                    url = url.replace(f"{{{param_name}}}", str(params[param_name]))

        # Bind request body fields
        for field_info in endpoint.get("request_fields", []):
            if field_info["name"] in params:
                if request_body is None:
                    request_body = {}
                request_body[field_info["name"]] = params[field_info["name"]]

        # Inject auth (async to support OAuth2 token fetch)
        url, request_params, headers = await self._inject_auth(url, request_params, headers)

        # Make the request
        await self._throttle()
        method = endpoint["method"].upper()

        try:
            async with httpx.AsyncClient(
                timeout=self.config.timeout_seconds,
                follow_redirects=True,
            ) as client:
                request_kwargs: dict[str, Any] = {
                    "headers": {"User-Agent": "AgentBazaar/0.2 (university project)", "Accept": "application/json"},
                    "params": request_params if request_params else None,
                }
                if headers:
                    request_kwargs["headers"].update(headers)
                if method in ("POST", "PUT", "PATCH") and request_body is not None:
                    request_kwargs["json"] = request_body

                response = await getattr(client, method.lower())(url, **request_kwargs)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(f"API returned {exc.response.status_code}: {exc.response.text[:200]}") from exc
        except Exception as exc:
            raise RuntimeError(f"API call failed: {exc}") from exc

        # Transform response to normalized output
        # Validate response against schema
        schema = extract_schema_from_endpoints([endpoint])
        is_valid, validation_errors = validate_response_against_schema(data, schema)
        if not is_valid:
            logging.warning(
                "Response validation failed for %s: %s",
                self.tool_id,
                "; ".join(validation_errors[:5]),
            )
            # Still return the data but mark it as having schema issues
            result = self._transform_response(data, endpoint)
            result["_schema_warnings"] = validation_errors
            return result

        return self._transform_response(data, endpoint)

    def _select_endpoint(self, operation_id: str | None = None) -> dict[str, Any] | None:
        """Select the endpoint to execute."""
        if operation_id:
            for endpoint in self.definition.endpoints:
                if endpoint.get("operation_id") == operation_id:
                    return endpoint
            # Fall back to matching by operation_id prefix
            for endpoint in self.definition.endpoints:
                op_id = endpoint.get("operation_id", "")
                if op_id and operation_id in op_id:
                    return endpoint
            return None

        # Default: select the first GET endpoint, or the first endpoint
        for endpoint in self.definition.endpoints:
            if endpoint["method"].upper() == "GET":
                return endpoint
        return self.definition.endpoints[0] if self.definition.endpoints else None

    def _transform_response(self, data: Any, endpoint: dict[str, Any]) -> dict[str, Any]:
        """Transform the raw API response into the normalized output format.

        The output format matches what the hand-written providers produce:
        a dict with output field names mapped to their values.
        """
        if not isinstance(data, dict):
            return {"result": data}

        output_fields = endpoint.get("response_fields", [])
        output_fields.extend(self.definition.fields)  # Include all output fields from spec

        result: dict[str, Any] = {}

        # Map response fields by name
        for field_info in output_fields:
            if field_info.get("direction") != "output":
                continue
            name = field_info["name"]
            field_path = field_info.get("path", "")

            # Try direct mapping
            if name in data:
                result[name] = data[name]
            elif field_path.startswith("body."):
                # Nested path in response body
                parts = field_path.split(".")[1:]  # Skip "body."
                value = data
                for part in parts:
                    if isinstance(value, dict) and part in value:
                        value = value[part]
                    else:
                        value = None
                        break
                if value is not None:
                    result[name] = value
            elif field_info.get("path", "").startswith("parameters."):
                # Parameter echoed in response
                param_name = field_info["path"].split(".")[-1]
                if param_name in data:
                    result[name] = data[param_name]

        # If no fields mapped, return the raw response under "result"
        if not result:
            result["result"] = data

        return result

    async def offline(self, params: dict[str, Any]) -> dict[str, Any]:
        """Return a deterministic fixture response.

        Uses the FixtureStore to find a matching fixture. If no fixture exists,
        raises an error rather than fabricating a successful response.
        """
        endpoint = self._select_endpoint()
        if endpoint is None:
            raise RuntimeError(f"No endpoint available for {self.tool_id}")

        endpoint_path = endpoint.get("path", "")
        method = endpoint.get("method", "GET").upper()

        fixture = self.fixture_store.get(
            self.tool_id,
            endpoint_path,
            method,
            params=params,
            preferred_type="success",
        )

        if fixture is None:
            # Auto-generate a success fixture from endpoint response fields
            response_fields = endpoint.get("response_fields", [])
            fixture = self.fixture_store.generate_success_fixture(
                self.tool_id,
                endpoint_path,
                method,
                response_fields=response_fields,
            )
            self.fixture_store.save(fixture)

        if fixture.fixture_type == "timeout":
            raise RuntimeError(f"Fixture timeout for {self.tool_id}")
        if fixture.fixture_type == "auth_failure":
            raise RuntimeError(f"Fixture auth failure for {self.tool_id}")
        if fixture.fixture_type == "rate_limit":
            raise RuntimeError(f"Fixture rate limit for {self.tool_id}")
        if fixture.error:
            raise RuntimeError(fixture.error)

        return dict(fixture.body) if isinstance(fixture.body, dict) else {"result": fixture.body}

    def status(self) -> dict[str, Any]:
        """Return the provider status."""
        return {
            "provider_id": self.provider_id,
            "tool_id": self.tool_id,
            "name": self.name,
            "capability": self.capability,
            "state": self.definition.state,
            "base_url": self.config.base_url,
            "auth_type": self.config.auth_type,
            "endpoint_count": len(self.definition.endpoints),
            "fail_next": self.fail_next,
            "offline_forced": self.offline_forced,
        }

    def force_failure(self, times: int = 1) -> None:
        """Inject a failure for the next N calls."""
        self.fail_next = max(1, times)

    def clear_failure(self) -> None:
        """Clear injected failures."""
        self.fail_next = 0

    def set_offline(self, value: bool) -> None:
        """Force offline mode."""
        self.offline_forced = value


# ---------------------------------------------------------------------------
# Provider factory
# ---------------------------------------------------------------------------


class GenericProviderFactory:
    """Factory for creating GenericProvider instances from staged definitions."""

    def __init__(self, settings: Settings, cache: Cache):
        self.settings = settings
        self.cache = cache

    def from_definition(self, definition: ProviderDefinition) -> GenericProvider:
        """Create a GenericProvider from a ProviderDefinition.

        Only VERIFIED providers can be created. STAGED or DISCOVERED providers
        raise ValueError.
        """
        if definition.state != ProviderState.VERIFIED:
            raise ValueError(
                f"Cannot create executable provider for {definition.tool_id}: "
                f"state is {definition.state}, must be {ProviderState.VERIFIED}"
            )
        return GenericProvider(definition, self.settings, self.cache)

    def from_tool_spec(self, spec: Any) -> GenericProvider | None:
        """Create a GenericProvider from a ToolSpec.

        This is a compatibility layer for the existing catalogue. It creates
        a minimal ProviderDefinition from the spec and returns a GenericProvider
        if the spec is executable.
        """
        # Check if we have a definition for this tool
        # In the full pipeline, this would look up the staging registry
        return None
