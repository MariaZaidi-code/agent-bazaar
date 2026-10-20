"""Factory helpers for the shared vector service."""

from __future__ import annotations

from agent_bazaar.config import Settings
from agent_bazaar.vec.embedder import build_embedder
from agent_bazaar.vec.index import VectorService

__all__ = ["VectorService", "build_vector_service"]


def build_vector_service(settings: Settings | None = None, force_fallback: bool = False) -> VectorService:
    return VectorService(build_embedder(settings=settings, force_fallback=force_fallback))
