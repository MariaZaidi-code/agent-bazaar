"""Discovery mapper facade: adapts the application's mapper to the pipeline.

The discovery pipeline needs a mapper object that exposes
``map_fields(MapRequest) -> MapResult``. The app's ``KnowledgeMapper``
class does not expose that method directly, but it holds a real
``MapperAgent`` under ``.mapper`` which does. This facade exposes that
path when available and otherwise raises, so the pipeline can report
honestly that mapping was unavailable.
"""

from __future__ import annotations

from typing import Any

from app.discovery.service import ProviderDefinition


class DiscoveryMapper:
    """Thin facade over the app's mapper that the discovery pipeline can call.

    * If the underlying mapper exposes a ``map_fields`` method it is used
      directly.
    * Otherwise the facade tries the wrapped ``.mapper`` attribute (the
      ``KnowledgeMapper`` convention). If that also lacks ``map_fields`` it
      raises ``RuntimeError``, which the pipeline reports as "mapping skipped".
    """

    def __init__(self, mapper: Any) -> None:
        self._mapper = mapper

    def _resolve(self) -> Any:
        if callable(getattr(self._mapper, "map_fields", None)):
            return self._mapper
        inner = getattr(self._mapper, "mapper", None)
        if callable(getattr(inner, "map_fields", None)):
            return inner
        raise RuntimeError("No mapper available")

    def map_fields(self, request: Any) -> Any:
        """Forward a mapping request to the real mapper agent."""
        return self._resolve().map_fields(request)

    async def map_provider(self, definition: ProviderDefinition, **kwargs: Any) -> dict[str, Any]:
        """Run the pipeline's existing ``map_provider_to_ontology`` helper."""
        from app.discovery.service import map_provider_to_ontology

        return await map_provider_to_ontology(definition, mapper=self._mapper, **kwargs)
