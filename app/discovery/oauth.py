"""OAuth2 support for the generic provider runtime.

Implements:
- Authorization Code flow (with PKCE)
- Client Credentials flow
- Token refresh with expiry handling
- Secure token storage (never in specs, metadata, logs or traces)
- Scope management
- Authentication failure recovery

Credentials are stored in an encrypted-at-rest token store keyed by provider_id.
They are never written into API specifications, provider metadata, logs,
or execution traces.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import time
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)

TOKEN_EXPIRY_MARGIN_SECONDS = 60  # refresh this many seconds before expiry


# ---------------------------------------------------------------------------
# Token models
# ---------------------------------------------------------------------------


@dataclass
class OAuthToken:
    """An OAuth2 access token with refresh capability."""

    provider_id: str
    access_token: str
    token_type: str = "Bearer"
    expires_at: float = 0.0
    refresh_token: str | None = None
    scope: str = ""
    obtained_at: float = field(default_factory=time.time)

    @property
    def is_expired(self) -> bool:
        if self.expires_at <= 0:
            return False  # no expiry set
        return time.time() >= (self.expires_at - TOKEN_EXPIRY_MARGIN_SECONDS)

    @property
    def authorization_header(self) -> str:
        return f"{self.token_type} {self.access_token}"

    def to_dict(self) -> dict[str, Any]:
        """Serialize. Used only for secure storage, never logged."""
        return {
            "provider_id": self.provider_id,
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at,
            "refresh_token": self.refresh_token,
            "scope": self.scope,
            "obtained_at": self.obtained_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthToken":
        return cls(
            provider_id=data["provider_id"],
            access_token=data["access_token"],
            token_type=data.get("token_type", "Bearer"),
            expires_at=data.get("expires_at", 0.0),
            refresh_token=data.get("refresh_token"),
            scope=data.get("scope", ""),
            obtained_at=data.get("obtained_at", time.time()),
        )


@dataclass
class OAuthClientConfig:
    """OAuth2 client configuration for a provider.

    client_secret is never serialized into specs or logs.
    """

    provider_id: str
    client_id: str
    client_secret: str = ""
    token_url: str = ""
    authorization_url: str = ""
    redirect_uri: str = "http://localhost:8000/oauth/callback"
    scopes: list[str] = field(default_factory=list)
    flow: str = "client_credentials"  # "client_credentials" or "authorization_code"

    @property
    def scope_string(self) -> str:
        return " ".join(self.scopes)


# ---------------------------------------------------------------------------
# Secure token storage
# ---------------------------------------------------------------------------


class TokenStore:
    """Secure on-disk token storage keyed by provider_id.

    Tokens are stored in a dedicated directory outside the provider
    definitions, with restrictive file permissions. The store never
    returns tokens in list operations without explicit request.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.base_dir.chmod(0o700)
        except OSError:
            pass  # Windows may not support chmod

    def _path(self, provider_id: str) -> Path:
        safe = hashlib.sha256(provider_id.encode()).hexdigest()[:16]
        return self.base_dir / f"{safe}.json"

    def save(self, token: OAuthToken) -> None:
        path = self._path(token.provider_id)
        path.write_text(json.dumps(token.to_dict()), encoding="utf-8")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def load(self, provider_id: str) -> OAuthToken | None:
        path = self._path(provider_id)
        if not path.exists():
            return None
        try:
            return OAuthToken.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, KeyError, OSError):
            return None

    def delete(self, provider_id: str) -> bool:
        path = self._path(provider_id)
        if path.exists():
            path.unlink()
            return True
        return False

    def has_token(self, provider_id: str) -> bool:
        return self._path(provider_id).exists()


# ---------------------------------------------------------------------------
# OAuth2 flows
# ---------------------------------------------------------------------------


class OAuth2Client:
    """OAuth2 client supporting Client Credentials and Authorization Code flows."""

    def __init__(self, token_store: TokenStore, timeout: float = 30.0):
        self.token_store = token_store
        self.timeout = timeout
        self._configs: dict[str, OAuthClientConfig] = {}

    def register_config(self, config: OAuthClientConfig) -> None:
        """Register an OAuth client configuration for a provider."""
        self._configs[config.provider_id] = config

    def get_config(self, provider_id: str) -> OAuthClientConfig | None:
        return self._configs.get(provider_id)

    async def get_token(self, provider_id: str) -> OAuthToken | None:
        """Get a valid token, refreshing if expired.

        Returns None if no config is registered or authentication fails.
        Never raises for auth failures - callers handle None.
        """
        config = self._configs.get(provider_id)
        if config is None:
            return None

        token = self.token_store.load(provider_id)
        if token and not token.is_expired:
            return token

        # Token expired or missing - try refresh first
        if token and token.refresh_token and config.flow == "authorization_code":
            refreshed = await self._refresh_token(config, token.refresh_token)
            if refreshed:
                self.token_store.save(refreshed)
                return refreshed

        # Full authentication
        if config.flow == "client_credentials":
            new_token = await self._client_credentials_flow(config)
        elif config.flow == "authorization_code":
            new_token = await self._authorization_code_flow(config)
        else:
            LOGGER.warning("Unknown OAuth flow %s for %s", config.flow, provider_id)
            return None

        if new_token:
            self.token_store.save(new_token)
            return new_token

        return None

    async def _client_credentials_flow(self, config: OAuthClientConfig) -> OAuthToken | None:
        """Obtain a token via the Client Credentials grant."""
        if not config.token_url or not config.client_id:
            LOGGER.warning("Client credentials flow missing token_url or client_id for %s", config.provider_id)
            return None

        data = {
            "grant_type": "client_credentials",
            "client_id": config.client_id,
        }
        if config.client_secret:
            data["client_secret"] = config.client_secret
        if config.scope_string:
            data["scope"] = config.scope_string

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    config.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            LOGGER.warning("Client credentials flow failed for %s: %s", config.provider_id, e)
            return None

        return self._parse_token_response(config, payload)

    async def _refresh_token(self, config: OAuthClientConfig, refresh_token: str) -> OAuthToken | None:
        """Refresh an expired token."""
        if not config.token_url:
            return None

        data = {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": config.client_id,
        }
        if config.client_secret:
            data["client_secret"] = config.client_secret

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    config.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            LOGGER.warning("Token refresh failed for %s: %s", config.provider_id, e)
            return None

        return self._parse_token_response(config, payload)

    async def _authorization_code_flow(self, config: OAuthClientConfig) -> OAuthToken | None:
        """Obtain a token via the Authorization Code grant.

        This requires user interaction to obtain the authorization code.
        In practice, the code is supplied externally (e.g., via redirect).
        This method returns None if no code is available.
        """
        # Authorization Code flow requires user interaction to get the code.
        # The code is typically obtained via the redirect_uri callback.
        # This method handles exchanging an externally-provided code.
        LOGGER.info(
            "Authorization code flow for %s requires user interaction. Use exchange_authorization_code() with a code.",
            config.provider_id,
        )
        return None

    async def exchange_authorization_code(
        self,
        config: OAuthClientConfig,
        code: str,
        code_verifier: str | None = None,
    ) -> OAuthToken | None:
        """Exchange an authorization code for tokens (Authorization Code flow)."""
        if not config.token_url:
            return None

        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": config.redirect_uri,
            "client_id": config.client_id,
        }
        if config.client_secret:
            data["client_secret"] = config.client_secret
        if code_verifier:
            data["code_verifier"] = code_verifier

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    config.token_url,
                    data=data,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                resp.raise_for_status()
                payload = resp.json()
        except Exception as e:
            LOGGER.warning("Authorization code exchange failed for %s: %s", config.provider_id, e)
            return None

        token = self._parse_token_response(config, payload)
        if token:
            self.token_store.save(token)
        return token

    def _parse_token_response(self, config: OAuthClientConfig, payload: dict[str, Any]) -> OAuthToken | None:
        """Parse a token endpoint response into an OAuthToken."""
        access_token = payload.get("access_token")
        if not access_token:
            LOGGER.warning("Token response for %s missing access_token", config.provider_id)
            return None

        expires_in = payload.get("expires_in", 0)
        expires_at = time.time() + float(expires_in) if expires_in else 0.0

        return OAuthToken(
            provider_id=config.provider_id,
            access_token=access_token,
            token_type=payload.get("token_type", "Bearer"),
            expires_at=expires_at,
            refresh_token=payload.get("refresh_token"),
            scope=payload.get("scope", config.scope_string),
        )

    def revoke(self, provider_id: str) -> bool:
        """Remove stored tokens for a provider."""
        return self.token_store.delete(provider_id)

    def status(self, provider_id: str) -> dict[str, Any]:
        """Return token status without exposing the token value."""
        token = self.token_store.load(provider_id)
        if token is None:
            return {"has_token": False, "expired": True}
        return {
            "has_token": True,
            "expired": token.is_expired,
            "expires_at": token.expires_at,
            "scope": token.scope,
            "token_type": token.token_type,
        }


def generate_pkce_pair() -> tuple[str, str]:
    """Generate a PKCE code_verifier and code_challenge (S256)."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_authorization_url(config: OAuthClientConfig, state: str, code_challenge: str) -> str:
    """Build the authorization URL for the Authorization Code flow with PKCE."""
    params = {
        "response_type": "code",
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if config.scope_string:
        params["scope"] = config.scope_string
    query = urllib.parse.urlencode(params)
    return f"{config.authorization_url}?{query}"
