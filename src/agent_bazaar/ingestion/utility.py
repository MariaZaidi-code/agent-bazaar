"""Deterministic ingestion entry point for OpenAPI, PDF, DOCX, and text sources."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, cast

from agent_bazaar.config import IngestionSettings, get_settings
from agent_bazaar.ingestion.documents import parse_document
from agent_bazaar.ingestion.listing_metadata import extract_listing_metadata
from agent_bazaar.ingestion.models import IngestionErrorInfo, NormalizedSpec
from agent_bazaar.ingestion.openapi import load_spec_document, parse_openapi
from agent_bazaar.protocols import IngestionError

_OPENAPI_FORMATS = frozenset({"openapi_json", "openapi_yaml"})
_SUFFIX_FORMATS: dict[str, str] = {
    ".json": "openapi_json",
    ".yaml": "openapi_yaml",
    ".yml": "openapi_yaml",
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "text",
    ".md": "text",
}
_FORMAT_ALIASES: dict[str, str] = {
    "openapi_json": "openapi_json",
    "json": "openapi_json",
    "openapi_yaml": "openapi_yaml",
    "yaml": "openapi_yaml",
    "yml": "openapi_yaml",
    "pdf": "pdf",
    "docx": "docx",
    "text": "text",
    "txt": "text",
    "md": "text",
    "markdown": "text",
}


def derive_tool_id(path: str | Path) -> str:
    stem = Path(path).stem.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", stem)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug or "tool"


def _resolve_format(path: Path, spec_format: str) -> str:
    requested = spec_format.strip().lower()
    if requested and requested != "auto":
        resolved = _FORMAT_ALIASES.get(requested)
        if resolved is None:
            raise IngestionError(
                "unsupported_format",
                f"Unsupported spec_format: {spec_format}",
                source=str(path),
                details={"spec_format": spec_format},
            )
        return resolved
    suffix = path.suffix.lower()
    resolved = _SUFFIX_FORMATS.get(suffix)
    if resolved is None:
        raise IngestionError(
            "unsupported_format",
            f"Unsupported file suffix: {suffix or '<none>'}",
            source=str(path),
            details={"suffix": suffix},
        )
    return resolved


class IngestionUtility:
    def __init__(self, settings: IngestionSettings | None = None) -> None:
        self.settings = settings if settings is not None else get_settings().ingestion

    def ingest(self, source: str | Path, spec_format: str = "auto") -> NormalizedSpec:
        path = Path(source)
        resolved = _resolve_format(path, spec_format)
        document: dict | None = None
        try:
            if resolved in _OPENAPI_FORMATS:
                raw_text = path.read_text(encoding="utf-8", errors="replace")
                document = load_spec_document(path, raw_text, resolved)
                spec = parse_openapi(path, raw_text, resolved, document)
            else:
                document_kind = cast(Literal["pdf", "docx", "text"], resolved)
                spec = parse_document(path, document_kind, self.settings)
        except IngestionError:
            raise
        except FileNotFoundError as exc:
            raise IngestionError(
                "file_not_found",
                f"Source file not found: {path}",
                source=str(path),
            ) from exc
        except OSError as exc:
            raise IngestionError(
                "read_error",
                f"Could not read source file: {exc}",
                source=str(path),
                details={"exception": type(exc).__name__},
            ) from exc
        spec.tool_id = derive_tool_id(path)
        spec.source = str(path)
        spec.spec_format = cast(
            Literal["openapi_json", "openapi_yaml", "pdf", "docx", "text"],
            resolved,
        )
        metadata = dict(spec.metadata)
        metadata["source"] = str(path)
        metadata["spec_format"] = resolved
        if resolved in _OPENAPI_FORMATS:
            metadata["endpoint_count"] = len(spec.endpoints)
            metadata["field_count"] = len(spec.fields)
        if document is not None:
            metadata["listing"] = extract_listing_metadata(document, spec.tool_id).model_dump()
        spec.metadata = metadata
        if getattr(spec, "retrieved_at", None) is None:
            spec.retrieved_at = datetime.now(timezone.utc)
        return spec

    def try_ingest(
        self,
        source: str | Path,
        spec_format: str = "auto",
    ) -> tuple[NormalizedSpec | None, IngestionErrorInfo | None]:
        try:
            return self.ingest(source, spec_format), None
        except IngestionError as exc:
            return None, IngestionErrorInfo(
                code=exc.code,
                message=exc.message,
                source=exc.source,
                details=dict(exc.details),
            )
        except Exception as exc:
            return None, IngestionErrorInfo(
                code="internal_error",
                message=f"Unexpected ingestion failure: {exc}",
                source=str(source),
                details={"exception": type(exc).__name__},
            )
