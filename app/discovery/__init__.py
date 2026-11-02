"""Discovery module: automated API discovery, staging, and generic execution.

This module provides:

- service.py: DiscoveryService - fetches, parses, and stages API specs
- staging.py: StagingRegistry - lifecycle management for discovered providers
- runtime.py: GenericProvider - executes APIs from parsed specs
- api.py: Discovery API endpoints
- media.py: Response models for the discovery API
- _legacy.py: Legacy discovery module (CURATED_APIS, sync_discovered)
"""

from __future__ import annotations

from app.discovery.service import (
    DiscoveryService,
    ProviderDefinition,
    ProviderState,
)
from app.discovery.staging import StagingRegistry
from app.discovery.runtime import GenericProvider, GenericProviderFactory, GenericProviderConfig
from app.discovery.fixtures import FixtureStore, Fixture
from app.discovery.oauth import OAuth2Client, OAuthClientConfig, TokenStore, OAuthToken
from app.discovery.pipeline import DiscoveryPipeline, PipelineResult
from app.discovery._legacy import CURATED_APIS, sync_discovered

__all__ = [
    "DiscoveryService",
    "ProviderDefinition",
    "ProviderState",
    "StagingRegistry",
    "GenericProvider",
    "GenericProviderFactory",
    "GenericProviderConfig",
    "FixtureStore",
    "Fixture",
    "OAuth2Client",
    "OAuthClientConfig",
    "TokenStore",
    "OAuthToken",
    "DiscoveryPipeline",
    "PipelineResult",
    "CURATED_APIS",
    "sync_discovered",
]
