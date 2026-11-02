"""Discovery API: HTTP endpoints for the discovery pipeline.

These endpoints expose the discovery, staging, and verification pipeline
to both the web interface and programmatic clients.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile, File

from app.discovery.service import ProviderState
from app.discovery.staging import StagingRegistry
from app.discovery.mapping import DiscoveryMapper


def register_discovery_routes(
    app: Any,
    staging: StagingRegistry,
    mapper: DiscoveryMapper | None = None,
    store: Any = None,
    retriever: Any = None,
    auditor: Any = None,
    provider_registry: Any = None,
    settings: Any = None,
) -> None:
    """Register discovery API routes on the FastAPI app.

    The optional lifecycle components are used by the integrated pipeline
    endpoints (/run, /pipeline/run, /verify-auditor/{tool_id}, /map/{tool_id})
    so those endpoints report honest outcomes instead of always returning
    ``"mapper": None``.
    """

    @app.get("/api/discovery")
    async def discovery_status() -> dict[str, Any]:
        """Return the current state of the discovery registry."""
        return {
            "stats": staging.stats(),
            "providers": [
                {
                    "tool_id": p.tool_id,
                    "name": p.name,
                    "provider_id": p.provider_id,
                    "state": p.state,
                    "capabilities": p.capabilities,
                    "base_url": p.base_url,
                    "discovered_at": p.discovered_at,
                    "staged_at": p.staged_at,
                    "verified_at": p.verified_at,
                    "duplicate_of": p.duplicate_of,
                    "suspended_reason": p.suspended_reason,
                    "endpoint_count": len(p.endpoints),
                    "fields": len(p.fields),
                }
                for p in staging.all()
            ],
        }

    @app.get("/api/discovery/staged")
    async def discovery_staged() -> dict[str, Any]:
        """Return all staged (awaiting verification) providers."""
        return {
            "providers": [
                {
                    "tool_id": p.tool_id,
                    "name": p.name,
                    "provider_id": p.provider_id,
                    "state": p.state,
                    "capabilities": p.capabilities,
                    "base_url": p.base_url,
                    "discovered_at": p.discovered_at,
                    "staged_at": p.staged_at,
                    "endpoint_count": len(p.endpoints),
                    "fields": len(p.fields),
                    "listing_metadata": (p.listing_metadata.model_dump() if p.listing_metadata else None),
                }
                for p in staging.staged()
            ],
        }

    @app.get("/api/discovery/verified")
    async def discovery_verified() -> dict[str, Any]:
        """Return all verified providers ready for execution."""
        return {
            "providers": [
                {
                    "tool_id": p.tool_id,
                    "name": p.name,
                    "provider_id": p.provider_id,
                    "state": p.state,
                    "capabilities": p.capabilities,
                    "base_url": p.base_url,
                    "discovered_at": p.discovered_at,
                    "verified_at": p.verified_at,
                    "endpoint_count": len(p.endpoints),
                }
                for p in staging.verified()
            ],
        }

    @app.get("/api/discovery/suspended")
    async def discovery_suspended() -> dict[str, Any]:
        """Return all suspended providers."""
        return {
            "providers": [
                {
                    "tool_id": p.tool_id,
                    "name": p.name,
                    "provider_id": p.provider_id,
                    "state": p.state,
                    "suspended_reason": p.suspended_reason,
                    "verification_notes": p.verification_notes,
                }
                for p in staging.suspended()
            ],
        }

    @app.post("/api/discovery/run")
    async def discovery_run(source: str = "apis-guru", limit: int = 50) -> dict[str, Any]:
        """Run discovery across configured sources.

        Fetches specifications from the configured source, parses them,
        deduplicates against the existing catalogue, and returns newly
        discovered providers in the DISCOVERED state.
        """
        sources = [{"type": source}]
        existing_tools = []  # In the full pipeline, load from graph

        discovered = staging._service.run_discovery(
            sources=sources,
            existing_tools=existing_tools,
            limit_per_source=limit,
        )

        for provider in discovered:
            staging.register(provider)

        return {
            "discovered": len(discovered),
            "providers": [
                {
                    "tool_id": p.tool_id,
                    "name": p.name,
                    "provider_id": p.provider_id,
                    "state": p.state,
                    "capabilities": p.capabilities,
                    "base_url": p.base_url,
                    "duplicate_of": p.duplicate_of,
                }
                for p in discovered
            ],
        }

    @app.post("/api/discovery/stage")
    async def discovery_stage_batch(tool_ids: list[str] | None = None) -> dict[str, Any]:
        """Stage one or more discovered providers.

        Moves providers from DISCOVERED to STAGED state. If tool_ids is None,
        stages all discovered providers.
        """
        if tool_ids is None:
            staged = staging.stage_all()
        else:
            staged = []
            for tool_id in tool_ids:
                provider = staging.get(tool_id)
                if provider is None:
                    raise HTTPException(status_code=404, detail=f"Provider {tool_id} not found")
                if provider.state != ProviderState.DISCOVERED:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Provider {tool_id} is not in DISCOVERED state",
                    )
                staged.append(staging._service.stage(provider))
                staging.register(staged[-1])

        return {
            "staged": len(staged),
            "providers": [{"tool_id": p.tool_id, "state": p.state, "staged_at": p.staged_at} for p in staged],
        }

    @app.post("/api/discovery/verify")
    async def discovery_verify_batch(
        tool_ids: list[str] | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        """Verify one or more staged providers.

        Moves providers from STAGED to VERIFIED state.
        Use /api/discovery/verify-with-auditor for Auditor-based verification.

        Args:
            tool_ids: Optional list of tool_ids to verify.
            force: If True, skip verification checks and mark as verified.
        """
        if tool_ids is None:
            providers = staging.staged()
        else:
            providers = []
            for tool_id in tool_ids:
                provider = staging.get(tool_id)
                if provider is None:
                    raise HTTPException(status_code=404, detail=f"Provider {tool_id} not found")
                if provider.state != ProviderState.STAGED:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Provider {tool_id} is not in STAGED state",
                    )
                providers.append(provider)

        verified = []
        for provider in providers:
            if force:
                notes = ["verification skipped (forced)"]
            else:
                notes = ["pending Auditor verification"]
            verified_provider = staging._service.verify(provider, checks=notes)
            staging.register(verified_provider)
            verified.append(verified_provider)

        return {
            "verified": len(verified),
            "providers": [{"tool_id": p.tool_id, "state": p.state, "verified_at": p.verified_at} for p in verified],
        }

    @app.post("/api/discovery/suspend")
    async def discovery_suspend_batch(tool_ids: list[str], reason: str = "suspended by user") -> dict[str, Any]:
        """Suspend one or more providers."""
        suspended = []
        for tool_id in tool_ids:
            provider = staging.get(tool_id)
            if provider is None:
                raise HTTPException(status_code=404, detail=f"Provider {tool_id} not found")
            suspended_provider = staging._service.suspend(provider, reason)
            staging.register(suspended_provider)
            suspended.append(suspended_provider)

        return {
            "suspended": len(suspended),
            "providers": [
                {"tool_id": p.tool_id, "state": p.state, "suspended_reason": p.suspended_reason} for p in suspended
            ],
        }

    @app.post("/api/discovery/reactivate")
    async def discovery_reactivate_batch(tool_ids: list[str]) -> dict[str, Any]:
        """Reactivate suspended providers, moving them back to STAGED."""
        reactivated = []
        for tool_id in tool_ids:
            provider = staging.get(tool_id)
            if provider is None:
                raise HTTPException(status_code=404, detail=f"Provider {tool_id} not found")
            if provider.state != ProviderState.SUSPENDED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Provider {tool_id} is not in SUSPENDED state",
                )
            reactivated_provider = staging._service.reactivate(provider)
            staging.register(reactivated_provider)
            reactivated.append(reactivated_provider)

        return {
            "reactivated": len(reactivated),
            "providers": [{"tool_id": p.tool_id, "state": p.state, "staged_at": p.staged_at} for p in reactivated],
        }

    @app.post("/api/discovery/reset")
    async def discovery_reset() -> dict[str, Any]:
        """Reset the discovery registry.

        Clears all staged providers. Discovered providers are lost.
        """
        count = staging.clear_staged()
        staging._providers.clear()
        staging._by_provider.clear()
        staging._by_capability.clear()
        return {"cleared": count}

    @app.post("/api/discovery/upload")
    async def discovery_upload(
        file: UploadFile = File(...),
        source_name: str = "",
    ) -> dict[str, Any]:
        """Upload an API specification for ingestion.

        Accepts OpenAPI JSON/YAML, PDF, DOCX, or plain text documents.
        The file is saved to the uploads directory and can be processed
        by the discovery pipeline.
        """
        from app.config import BASE_DIR

        uploads_dir = BASE_DIR / "data" / "specs" / "uploads"
        uploads_dir.mkdir(parents=True, exist_ok=True)

        file_path = uploads_dir / file.filename
        content = await file.read()
        file_path.write_bytes(content)

        try:
            spec_content = content.decode("utf-8", errors="replace")
            if "openapi" in spec_content or "swagger" in spec_content:
                parsed = staging._service.parse_raw_openapi(content, source=str(file_path))
                if parsed:
                    definition = staging._service.discover(
                        content,
                        source=str(file_path),
                        existing_tools=[],
                    )
                    if definition:
                        staging.register(definition)
                        return {
                            "uploaded": file.filename,
                            "parsed": True,
                            "tool_id": definition.tool_id,
                            "state": definition.state,
                        }
        except Exception:
            pass

        return {
            "uploaded": file.filename,
            "parsed": False,
            "message": "File uploaded. Run discovery to parse and stage.",
        }

    @app.post("/api/discovery/ingest")
    async def discovery_ingest_spec(
        spec_url: str = "",
        spec_content: str = "",
    ) -> dict[str, Any]:
        """Ingest an API specification from a URL or raw content.

        This triggers discovery for a single spec: parse, deduplicate, and stage.
        """
        if spec_url:
            from agent_bazaar.ingestion.sources import ApisGuruSource

            try:
                source = ApisGuruSource(timeout=30)
                content = source.opener(spec_url).read()
                definition = staging._service.discover(
                    content,
                    source=spec_url,
                    existing_tools=[],
                )
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")
        elif spec_content:
            content = spec_content.encode("utf-8")
            definition = staging._service.discover(
                content,
                source="inline-content",
                existing_tools=[],
            )
        else:
            raise HTTPException(status_code=400, detail="Provide spec_url or spec_content")

        if definition is None:
            raise HTTPException(status_code=400, detail="Failed to parse specification")

        staging.register(definition)

        return {
            "discovered": True,
            "tool_id": definition.tool_id,
            "name": definition.name,
            "provider_id": definition.provider_id,
            "state": definition.state,
            "capabilities": definition.capabilities,
            "duplicate_of": definition.duplicate_of,
        }

    @app.get("/api/discovery/sources")
    async def discovery_list_sources() -> dict[str, Any]:
        """List configured discovery sources."""
        from app.discovery._legacy import CURATED_APIS
        from app.config import BASE_DIR

        return {
            "sources": [
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
                    "path": str(BASE_DIR / "data" / "specs" / "uploads"),
                },
                {
                    "type": "openapi-url",
                    "name": "Direct URL",
                    "description": "Fetch OpenAPI spec from any URL",
                },
            ]
        }

    @app.post("/api/discovery/verify-with-auditor")
    async def discovery_verify_with_auditor(tool_ids: list[str] | None = None) -> dict[str, Any]:
        """Verify providers using the Auditor."""
        if not hasattr(staging, "_scheduler"):
            staging._scheduler = ContinuousDiscoveryScheduler(
                staging._service,
                staging,
                staging.staging_dir.parent / "checkpoints",
            )

        providers_to_verify = []
        if tool_ids:
            for tool_id in tool_ids:
                provider = staging.get(tool_id)
                if provider and provider.state == ProviderState.STAGED:
                    providers_to_verify.append(provider)
        else:
            providers_to_verify = staging.staged()

        results = []
        for provider in providers_to_verify:
            try:
                from app.discovery.service import verify_provider_with_auditor

                audit_result = await verify_provider_with_auditor(
                    provider,
                    auditor=auditor,
                    settings=settings,
                )

                if audit_result.get("verified", False):
                    verified = staging._service.verify(provider, checks=audit_result.get("notes", []))
                    staging.register(verified)
                    results.append(
                        {"tool_id": provider.tool_id, "verified": True, "notes": audit_result.get("notes", [])}
                    )
                else:
                    results.append(
                        {"tool_id": provider.tool_id, "verified": False, "errors": audit_result.get("errors", [])}
                    )
            except Exception as e:
                results.append({"tool_id": provider.tool_id, "verified": False, "errors": [str(e)]})

        return {"verified": sum(1 for r in results if r.get("verified")), "results": results}

    @app.post("/api/discovery/pipeline/run")
    async def discovery_pipeline_run(
        spec_content: str = "",
        spec_url: str = "",
        source: str = "",
    ) -> dict[str, Any]:
        """Run a specification through the complete discovery-to-execution pipeline.

        Steps: discover -> stage -> map -> verify -> register -> persist.
        Returns a PipelineResult with honest per-step outcomes.
        """
        from app.discovery.pipeline import DiscoveryPipeline

        if spec_url:
            from agent_bazaar.ingestion.sources import ApisGuruSource

            try:
                fetcher = ApisGuruSource(timeout=30)
                content_bytes = fetcher.opener(spec_url).read()
                source = spec_url
            except Exception as exc:
                raise HTTPException(status_code=400, detail=f"Failed to fetch URL: {exc}")
        elif spec_content:
            content_bytes = spec_content.encode("utf-8")
            source = source or "inline-content"
        else:
            raise HTTPException(status_code=400, detail="Provide spec_content or spec_url")

        mapper_instance = mapper._mapper if mapper is not None else None

        pipeline = DiscoveryPipeline(
            staging=staging,
            settings=settings,
            mapper=mapper_instance,
            store=store,
            retriever=retriever,
            auditor=auditor,
            provider_registry=provider_registry,
        )

        result = await pipeline.run_full_pipeline(
            content_bytes,
            source=source,
            existing_tools=[],
        )

        return result.to_dict()

    @app.get("/api/discovery/pipeline/history")
    async def discovery_pipeline_history(tool_id: str = "") -> dict[str, Any]:
        """Get pipeline execution history, optionally filtered by tool_id."""
        from app.discovery.pipeline import DiscoveryPipeline

        pipeline = DiscoveryPipeline(
            staging=staging,
            settings=settings,
        )
        history = pipeline.get_history(tool_id if tool_id else None)
        return {"history": history, "count": len(history)}

    @app.get("/api/discovery/pipeline/status")
    async def discovery_pipeline_status() -> dict[str, Any]:
        """Get pipeline component status."""
        return {
            "staging_available": staging is not None,
            "providers_staged": len(staging.staged()) if staging else 0,
            "providers_verified": len(staging.verified()) if staging else 0,
            "components": {
                "mapper": mapper is not None,
                "store": store is not None,
                "retriever": retriever is not None,
                "auditor": auditor is not None,
                "provider_registry": provider_registry is not None,
            },
        }

    @app.post("/api/discovery/verify-auditor/{tool_id}")
    async def discovery_verify_single_with_auditor(tool_id: str) -> dict[str, Any]:
        """Verify a single provider using the full 4-level auditor verification."""
        provider = staging.get(tool_id)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"Provider {tool_id} not found")
        if provider.state != ProviderState.STAGED:
            raise HTTPException(
                status_code=400,
                detail=f"Provider {tool_id} must be in STAGED state, is {provider.state}",
            )

        from app.discovery.service import verify_provider_with_auditor

        result = await verify_provider_with_auditor(provider, auditor=auditor, settings=settings)

        if result.get("verified"):
            verified = staging._service.verify(provider, checks=result.get("notes", []))
            staging.register(verified)
        else:
            suspended = staging._service.suspend(
                provider,
                reason="; ".join(result.get("errors", ["verification failed"])),
            )
            staging.register(suspended)

        return result

    @app.post("/api/discovery/map/{tool_id}")
    async def discovery_map_single(tool_id: str) -> dict[str, Any]:
        """Run ontology mapping for a single provider."""
        provider = staging.get(tool_id)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"Provider {tool_id} not found")

        from app.discovery.service import map_provider_to_ontology

        mapper_instance = mapper._mapper if mapper is not None else None
        result = await map_provider_to_ontology(
            provider,
            mapper=mapper_instance,
            store=store,
            retriever=retriever,
        )
        return result

    @app.get("/api/discovery/scheduler/status")
    async def discovery_scheduler_status() -> dict[str, Any]:
        """Return the status of the continuous discovery scheduler."""
        if not hasattr(staging, "_scheduler"):
            return {"running": False, "error": "Scheduler not initialized"}
        return staging._scheduler.status()

    @app.post("/api/discovery/scheduler/start")
    async def discovery_scheduler_start(interval: int = 3600) -> dict[str, Any]:
        """Start the continuous discovery scheduler."""
        import asyncio

        if not hasattr(staging, "_scheduler"):
            from app.discovery.service import ContinuousDiscoveryScheduler

            staging._scheduler = ContinuousDiscoveryScheduler(
                staging._service,
                staging,
                staging.staging_dir.parent / "checkpoints",
                interval_seconds=interval,
            )
            staging._scheduler.configure_sources(
                [
                    {"type": "apis-guru", "limit": 20},
                ]
            )
        await staging._scheduler.start()
        return {"running": True, "message": "Scheduler started"}

    @app.post("/api/discovery/scheduler/stop")
    async def discovery_scheduler_stop() -> dict[str, Any]:
        """Stop the continuous discovery scheduler."""
        if hasattr(staging, "_scheduler") and staging._scheduler:
            await staging._scheduler.stop()
            return {"running": False, "message": "Scheduler stopped"}
        return {"running": False, "message": "Scheduler not running"}

    @app.post("/api/discovery/scheduler/run-now")
    async def discovery_scheduler_run_now() -> dict[str, Any]:
        """Run a discovery cycle immediately."""
        if not hasattr(staging, "_scheduler") or not staging._scheduler:
            return {"error": "Scheduler not initialized", "discovered": 0}
        result = await staging._scheduler.run_discovery_cycle()
        return result

    @app.get("/api/discovery/scheduler/checkpoint")
    async def discovery_scheduler_checkpoint() -> dict[str, Any]:
        """Return the discovery checkpoint info."""
        if not hasattr(staging, "_scheduler") or not staging._scheduler:
            return {"specs": 0}
        return {"specs": len(staging._scheduler._last_checkpoint)}

    @app.get("/api/discovery/export")
    async def discovery_export(path: str = "staging") -> dict[str, Any]:
        """Export the staging registry to a JSON file."""
        export_path = Path(path)
        staging.export_staging_json(export_path)
        return {"exported": str(export_path), "providers": staging.count_by_state()}

    @app.post("/api/discovery/import")
    async def discovery_import(path: str = "staging") -> dict[str, Any]:
        """Import providers from a staging JSON file."""
        import_path = Path(path)
        if not import_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {import_path}")
        count = staging.import_staging_json(import_path)
        return {"imported": count}


class ContinuousDiscoveryScheduler:
    """Kept in discovery/api.py for backward compatibility with legacy cron endpoints.

    New integrated pipeline uses the scheduler defined in ``app.discovery.service``.
    """

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
