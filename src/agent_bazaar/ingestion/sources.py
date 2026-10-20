"""Specification acquisition sources.

A *source* enumerates candidate specifications and fetches their bytes. The
corpus builder (``scripts/fetch_specs.py``) and the Mapper listing path both
work through this interface, so every specification carries the identifier and
the licence policy of the source that supplied it and provenance can be written
next to the extracted metadata.

Two sources ship with the project:

* :class:`ApisGuruSource` reads the public APIs.guru directory of community
  maintained OpenAPI documents.
* :class:`LocalUploadSource` reads provider-submitted specifications from a
  local directory, which is how a listing reaches the Mapper.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

import requests

APIS_GURU_LIST_URL = "https://api.apis.guru/v2/list.json"
USER_AGENT = "agent-bazaar-corpus/0.1"
MAX_SPEC_BYTES = 1_500_000
MARKER_WINDOW = 2000
SPEC_SUFFIXES = (".json", ".yaml", ".yml")
MANIFEST_NAME = "manifest.json"


class SourceError(RuntimeError):
    """Raised when a source cannot supply a usable specification."""


@runtime_checkable
class SpecSource(Protocol):
    """Contract implemented by every acquisition source."""

    name: str
    source_id: str
    licence_policy: str

    def list_candidates(self) -> list[dict[str, Any]]:
        """Return the candidate specifications in a deterministic order."""

    def fetch(self, entry: dict[str, Any]) -> bytes:
        """Return the raw bytes of one candidate specification."""


def http_get(url: str, timeout: int) -> bytes:
    """Fetch a URL and return its body."""
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.content


class BaseSpecSource(SpecSource, ABC):
    """Shared behaviour: identifiers, licence policy and payload checks."""

    name: str = ""
    source_id: str = ""
    licence_policy: str = ""
    max_bytes: int = MAX_SPEC_BYTES

    @abstractmethod
    def list_candidates(self) -> list[dict[str, Any]]:
        """Return the candidate specifications in a deterministic order."""

    @abstractmethod
    def fetch(self, entry: dict[str, Any]) -> bytes:
        """Return the raw bytes of one candidate specification."""

    def provenance(self) -> dict[str, str]:
        """Return the provenance facts that describe this source."""
        return {
            "source": self.source_id,
            "source_name": self.name,
            "licence_policy": self.licence_policy,
        }

    def check_payload(self, content: bytes) -> bytes:
        """Reject payloads that are too large or are not OpenAPI documents."""
        if len(content) > self.max_bytes:
            raise SourceError(f"spec too large ({len(content)} bytes)")
        body = content.decode("utf-8", errors="replace")
        if '"openapi"' not in body[:MARKER_WINDOW] and '"swagger"' not in body[:MARKER_WINDOW]:
            raise SourceError("not an OpenAPI document")
        return content


class ApisGuruSource(BaseSpecSource):
    """The APIs.guru directory of community maintained OpenAPI documents."""

    name = "apis-guru"
    source_id = "apis-guru"
    licence_policy = (
        "Third-party API descriptions published in the APIs.guru directory. Each document keeps the "
        "licence and terms declared by its own provider; redistribution needs the provider's permission."
    )

    def __init__(
        self,
        timeout: int = 30,
        opener: Callable[[str], bytes] | None = None,
        list_url: str = APIS_GURU_LIST_URL,
    ) -> None:
        self.timeout = timeout
        self.list_url = list_url
        self.opener = opener or (lambda url: http_get(url, timeout))

    def list_candidates(self) -> list[dict[str, Any]]:
        """Return one candidate per API, using the preferred version."""
        payload = self.opener(self.list_url)
        listing = json.loads(payload.decode("utf-8"))
        if not isinstance(listing, dict):
            raise SourceError("apis.guru listing is not an object")
        return self.entries_from_listing(listing)

    @staticmethod
    def entries_from_listing(listing: dict[str, Any]) -> list[dict[str, Any]]:
        """Turn an APIs.guru listing into deterministic candidate entries."""
        entries: list[dict[str, Any]] = []
        for key in sorted(listing):
            entry = listing[key]
            if not isinstance(entry, dict):
                continue
            preferred = entry.get("preferred")
            version = (entry.get("versions") or {}).get(preferred or "", {})
            url = version.get("swaggerUrl")
            info = version.get("info") or {}
            if not url:
                continue
            entries.append(
                {
                    "key": key,
                    "title": info.get("title") or key,
                    "categories": [str(item).lower() for item in (info.get("x-apisguru-categories") or [])],
                    "provider": info.get("x-apisguru-provider-name") or "",
                    "version": version.get("openapiVer") or preferred or "",
                    "url": url,
                }
            )
        return entries

    def fetch(self, entry: dict[str, Any]) -> bytes:
        """Download one candidate document."""
        url = str(entry.get("url") or "")
        if not url:
            raise SourceError("candidate entry has no url")
        return self.check_payload(self.opener(url))


class LocalUploadSource(BaseSpecSource):
    """Provider-submitted specifications stored in a local directory."""

    name = "local-upload"
    source_id = "local-upload"
    licence_policy = (
        "Specification submitted by the provider. The provider keeps the copyright and grants the "
        "use recorded in the document and in the listing metadata."
    )

    def __init__(self, root: str | Path, timeout: int = 30) -> None:
        self.root = Path(root)
        self.timeout = timeout

    def list_candidates(self) -> list[dict[str, Any]]:
        """Return one candidate per submitted specification file."""
        candidates: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("*")):
            if not path.is_file() or path.suffix.lower() not in SPEC_SUFFIXES:
                continue
            if path.name == MANIFEST_NAME:
                continue
            document = self.read_document(path)
            info = document.get("info") if isinstance(document.get("info"), dict) else {}
            candidates.append(
                {
                    "key": path.stem,
                    "title": str(info.get("title") or path.stem),
                    "categories": [str(item).lower() for item in (info.get("x-apisguru-categories") or [])],
                    "provider": str(info.get("x-apisguru-provider-name") or ""),
                    "version": str(info.get("version") or ""),
                    "url": "",
                    "file": path.name,
                    "path": str(path),
                }
            )
        return candidates

    def fetch(self, entry: dict[str, Any]) -> bytes:
        """Read one submitted specification from disk."""
        path = Path(str(entry.get("path") or ""))
        if not path.is_absolute():
            path = self.root / path
        if not path.is_file():
            raise SourceError(f"submitted specification not found: {path}")
        return self.check_payload(path.read_bytes())

    @staticmethod
    def read_document(path: Path) -> dict[str, Any]:
        """Parse a submitted specification so its metadata can be read."""
        text = path.read_text(encoding="utf-8", errors="replace")
        if path.suffix.lower() == ".json":
            try:
                document = json.loads(text)
            except json.JSONDecodeError:
                return {}
        else:
            try:
                import yaml
            except ModuleNotFoundError:  # pragma: no cover - PyYAML is a dependency
                return {}
            try:
                document = yaml.safe_load(text)
            except yaml.YAMLError:
                return {}
        return document if isinstance(document, dict) else {}
