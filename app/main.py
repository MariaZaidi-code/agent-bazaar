from __future__ import annotations

import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import BASE_DIR, Settings
from app.core.observability import RequestMetrics, SlidingWindowRateLimiter
from app.core.versioning import build_version_manifest
from app.schemas import (
    CorrectionRequest,
    HealthResponse,
    ListingIngestRequest,
    TaskResult,
    new_id,
)
from app.services import AppServices, build_services

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
ASSET_VERSION = str(
    int(max((STATIC_DIR / name).stat().st_mtime for name in ("styles.css", "premium.css", "app.js")))
)
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


class TaskInput(BaseModel):
    task: str = Field(min_length=3, max_length=1500)
    document_id: str | None = Field(default=None, min_length=1, max_length=80)


class FailNextInput(BaseModel):
    times: int = Field(default=1, ge=1, le=10)


class WebhookInput(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    events: list[str] = Field(default_factory=lambda: ["task.completed"])
    secret: str = Field(default="", max_length=256)


class JobInput(BaseModel):
    kind: str = Field(pattern="^(export_graph|export_graph_jsonld|reset_demo)$")


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or Settings()
    request_metrics = RequestMetrics()
    rate_limiter = SlidingWindowRateLimiter(
        limit=resolved_settings.rate_limit_requests,
        window_seconds=resolved_settings.rate_limit_window_seconds,
    )
    request_logger = logging.getLogger("agent_bazaar.http")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.services = build_services(resolved_settings)
        application.state.started_at = time.time()
        try:
            yield
        finally:
            application.state.services.shutdown()

    application = FastAPI(
        title="Agent Bazaar",
        version=__version__,
        description="Ontology- and knowledge-graph-driven agent marketplace.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @application.middleware("http")
    async def observe_request(request: Request, call_next):
        path = request.url.path
        correlation_id = request.headers.get("X-Correlation-ID") or new_id("req")
        request.state.correlation_id = correlation_id
        client_key = request.client.host if request.client else "anonymous"
        exempt = path in {"/api/health", "/api/health/ready", "/api/metrics"}
        exempt = exempt or path.startswith("/api/admin/")
        if resolved_settings.rate_limit_enabled and not exempt:
            allowed, retry_after = rate_limiter.allow(client_key)
            if not allowed:
                request_metrics.record(request.method, path, 429, 0.0)
                return JSONResponse(
                    status_code=429,
                    content={"detail": "Too many requests", "retry_after_seconds": round(retry_after, 2)},
                    headers={
                        "X-Correlation-ID": correlation_id,
                        "Retry-After": str(max(1, int(retry_after + 0.999))),
                        "X-RateLimit-Limit": str(resolved_settings.rate_limit_requests),
                    },
                )
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000.0
            request_metrics.record(request.method, path, 500, duration_ms)
            request_logger.exception(
                json.dumps({"correlation_id": correlation_id, "method": request.method, "path": path})
            )
            raise
        duration_ms = (time.perf_counter() - started) * 1000.0
        request_metrics.record(request.method, path, response.status_code, duration_ms)
        response.headers["X-Correlation-ID"] = correlation_id
        response.headers["X-Response-Time-Ms"] = f"{duration_ms:.3f}"
        request_logger.info(
            json.dumps(
                {
                    "correlation_id": correlation_id,
                    "method": request.method,
                    "path": path,
                    "status": response.status_code,
                    "duration_ms": round(duration_ms, 3),
                }
            )
        )
        return response

    def services(request: Request) -> AppServices:
        return request.app.state.services

    def render_page(request: Request, page: str, title: str) -> HTMLResponse:
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "version": __version__,
                "asset_version": ASSET_VERSION,
                "page": page,
                "page_title": title,
            },
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @application.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return render_page(request, "dashboard", "Workflow workspace")

    @application.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return render_page(request, "dashboard", "Workflow workspace")

    @application.get("/marketplace", response_class=HTMLResponse)
    async def marketplace(request: Request) -> HTMLResponse:
        return render_page(request, "marketplace", "Service marketplace")

    @application.get("/monitor", response_class=HTMLResponse)
    async def monitor(request: Request) -> HTMLResponse:
        return render_page(request, "monitor", "Self-healing monitor")

    @application.get("/library", response_class=HTMLResponse)
    async def library(request: Request) -> HTMLResponse:
        return render_page(request, "library", "Trust Center")

    @application.get("/documents", response_class=HTMLResponse)
    async def documents(request: Request) -> HTMLResponse:
        return render_page(request, "documents", "Documents")

    @application.get("/docs", response_class=HTMLResponse)
    async def documentation(request: Request) -> HTMLResponse:
        return render_page(request, "docs", "Documentation")

    @application.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @application.get("/api/health", response_model=HealthResponse)
    async def health(request: Request) -> HealthResponse:
        state = services(request)
        return HealthResponse(
            app=state.settings.app_name,
            version=__version__,
            mode="offline" if state.settings.offline_mode else "live",
            tools=len(state.graph.all()),
            llm_enabled=state.llm.enabled,
        )

    @application.get("/api/health/ready")
    async def ready(request: Request) -> dict[str, Any]:
        state = services(request)
        knowledge_available = state.knowledge is not None
        graph_ready = len(state.graph.all()) > 0
        ontology_ready = len(state.ontology.concepts) > 0
        ready_flag = graph_ready and ontology_ready
        return {
            "status": "ready" if ready_flag else "not_ready",
            "ready": ready_flag,
            "checks": {
                "graph": graph_ready,
                "ontology": ontology_ready,
                "knowledge_layer": knowledge_available,
            },
            "tools": len(state.graph.all()),
            "concepts": len(state.ontology.concepts),
        }

    @application.get("/api/metrics")
    async def metrics(request: Request) -> Response:
        state = services(request)
        providers = state.providers.all()
        trust_rows = state.trust.all()
        lines = [
            "# HELP agent_bazaar_tools Number of registered tools.",
            "# TYPE agent_bazaar_tools gauge",
            f"agent_bazaar_tools {len(state.graph.all())}",
            "# HELP agent_bazaar_providers Number of registered providers.",
            "# TYPE agent_bazaar_providers gauge",
            f"agent_bazaar_providers {len(providers)}",
            "# HELP agent_bazaar_trust_providers Number of providers with trust state.",
            "# TYPE agent_bazaar_trust_providers gauge",
            f"agent_bazaar_trust_providers {len(trust_rows)}",
            "# HELP agent_bazaar_breakers_open Number of open circuit breakers.",
            "# TYPE agent_bazaar_breakers_open gauge",
            f"agent_bazaar_breakers_open {sum(1 for item in state.breakers.snapshot() if item.get('state') == 'open')}",
        ]
        request_snapshot = request_metrics.snapshot()
        lines.extend(
            [
                "# HELP agent_bazaar_http_requests_total Number of HTTP requests served.",
                "# TYPE agent_bazaar_http_requests_total counter",
                f"agent_bazaar_http_requests_total {request_snapshot['requests']}",
                "# HELP agent_bazaar_http_errors_total Number of HTTP 5xx responses.",
                "# TYPE agent_bazaar_http_errors_total counter",
                f"agent_bazaar_http_errors_total {request_snapshot['errors']}",
            ]
        )
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4; charset=utf-8")

    @application.get("/api/admin/stats")
    async def admin_stats(request: Request) -> dict[str, Any]:
        state = services(request)
        started_at = float(getattr(request.app.state, "started_at", time.time()))
        return {
            "version": __version__,
            "uptime_seconds": round(time.time() - started_at, 3),
            "mode": "offline" if state.settings.offline_mode else "live",
            "requests": request_metrics.snapshot(),
            "jobs": state.jobs.list(limit=20),
            "webhooks": state.webhooks.list(),
            "knowledge_available": state.knowledge is not None,
            "rate_limit": {
                "enabled": state.settings.rate_limit_enabled,
                "requests": state.settings.rate_limit_requests,
                "window_seconds": state.settings.rate_limit_window_seconds,
            },
        }

    @application.get("/api/admin/versions")
    async def admin_versions(request: Request) -> dict[str, Any]:
        state = services(request)
        return build_version_manifest(
            state.settings,
            ontology_concepts=len(state.ontology.concepts),
            graph_tools=len(state.graph.all()),
        )

    @application.post("/api/admin/cache/clear")
    async def admin_clear_cache(request: Request) -> dict[str, Any]:
        services(request).cache.clear()
        return {"status": "cleared"}

    @application.get("/api/admin/webhooks")
    async def admin_list_webhooks(request: Request) -> dict[str, Any]:
        return {"webhooks": services(request).webhooks.list()}

    @application.post("/api/admin/webhooks")
    async def admin_create_webhook(payload: WebhookInput, request: Request) -> dict[str, Any]:
        try:
            webhook = services(request).webhooks.register(
                payload.url,
                events=payload.events,
                secret=payload.secret,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"webhook": webhook}

    @application.delete("/api/admin/webhooks/{webhook_id}")
    async def admin_delete_webhook(webhook_id: str, request: Request) -> dict[str, Any]:
        if not services(request).webhooks.delete(webhook_id):
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"deleted": True, "webhook_id": webhook_id}

    @application.get("/api/admin/jobs")
    async def admin_list_jobs(request: Request, limit: int = Query(default=20, ge=1, le=100)) -> dict[str, Any]:
        return {"jobs": services(request).jobs.list(limit=limit)}

    @application.get("/api/admin/jobs/{job_id}")
    async def admin_get_job(job_id: str, request: Request) -> dict[str, Any]:
        job = services(request).jobs.get(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return {"job": job}

    @application.post("/api/admin/jobs")
    async def admin_submit_job(payload: JobInput, request: Request) -> dict[str, Any]:
        state = services(request)
        functions = {
            "export_graph": state.export_graph,
            "export_graph_jsonld": state.export_graph_jsonld,
            "reset_demo": state.reset_demo,
        }
        job = state.jobs.submit(payload.kind, functions[payload.kind])
        return {"job": job}

    @application.get("/api/admin/graph.jsonld")
    async def admin_export_graph_jsonld(request: Request) -> dict[str, Any]:
        state = services(request)
        exported = state.export_graph_jsonld()
        if not exported:
            raise HTTPException(status_code=503, detail="JSON-LD export unavailable")
        return {"exported": True, "path": str(state.settings.runtime_dir / "knowledge_graph.jsonld")}

    @application.get("/api/ontology")
    async def ontology(request: Request) -> dict[str, Any]:
        state = services(request)
        return {
            "summary": state.ontology.summary(),
            "concepts": [
                state.ontology.concept_payload(name)
                for name in sorted(state.ontology.concepts)
            ],
            "units": [
                state.ontology.unit_payload(name) for name in sorted(state.ontology.units)
            ],
            "capabilities": state.ontology.capabilities,
        }

    @application.get("/api/knowledge")
    async def knowledge(request: Request) -> dict[str, Any]:
        state = services(request)
        layer = state.knowledge
        if layer is None:
            return {
                "available": False,
                "backend": state.settings.knowledge_backend,
                "reason": "knowledge layer artifacts are not available",
            }
        store = layer.store
        stats = store.describe_graph()
        return {
            "available": True,
            "backend": state.settings.knowledge_backend,
            "graph": stats,
            "concepts": len(store.list_concepts()),
            "tools": [summary.model_dump(mode="json") for summary in store.list_tools()],
            "graph_file": str(state.settings.knowledge_graph_file),
            "ontology_file": str(state.settings.knowledge_ontology_file),
        }

    @application.get("/api/tools")
    async def tools(request: Request) -> dict[str, Any]:
        state = services(request)
        trust_rows = {item["provider_id"]: item for item in state.trust.all()}
        payload = []
        for tool in state.graph.all():
            data = tool.model_dump(mode="json")
            data["trust"] = trust_rows.get(tool.provider_id, {}).get("score", 0.5)
            data["demoted"] = trust_rows.get(tool.provider_id, {}).get("demoted", False)
            data["breaker"] = state.breakers.state(
                state.breakers.link_key("client", tool.provider_id)
            ).value
            data["validation"] = state.providers.validation.get(tool.id, [])
            data["auditor_tool_id"] = state.auditor.catalog_tool_id(tool.id) or ""
            payload.append(data)
        return {"tools": payload, "count": len(payload)}

    @application.post("/api/tasks", response_model=TaskResult)
    async def run_task(
        payload: TaskInput,
        request: Request,
        background_tasks: BackgroundTasks,
    ) -> TaskResult:
        state = services(request)
        if payload.document_id and state.providers.document_store.get(payload.document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found")
        result = await state.client.run(payload.task, document_id=payload.document_id)
        background_tasks.add_task(
            state.webhooks.dispatch,
            "task.completed",
            {
                "task_id": result.task_id,
                "status": result.status.value,
                "answer": result.answer,
                "correlation_id": getattr(request.state, "correlation_id", ""),
            },
        )
        return result

    @application.get("/api/tasks/recent")
    async def recent_tasks(request: Request, limit: int = Query(default=15, ge=1, le=100)):
        return {"tasks": services(request).traces.list_results(limit=limit)}

    @application.get("/api/tasks/{task_id}", response_model=TaskResult)
    async def get_task(task_id: str, request: Request) -> TaskResult:
        result = services(request).traces.get_result(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Task not found")
        result.trace = services(request).traces.events(task_id)
        return result

    @application.get("/api/tasks/{task_id}/messages")
    async def task_messages(task_id: str, request: Request) -> dict[str, Any]:
        state = services(request)
        if state.traces.get_result(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        return {"messages": state.traces.messages(task_id)}

    @application.get("/api/monitoring")
    async def monitoring(request: Request) -> dict[str, Any]:
        return services(request).monitoring()

    @application.get("/api/auditor")
    async def auditor_overview(request: Request) -> dict[str, Any]:
        return services(request).auditor.overview()

    @application.get("/api/auditor/trust")
    async def auditor_trust(request: Request) -> dict[str, Any]:
        return services(request).auditor.trust_payload()

    @application.post("/api/auditor/verify/{tool_id}")
    async def auditor_verify(
        tool_id: str,
        request: Request,
        live: bool = Query(default=False),
    ) -> dict[str, Any]:
        try:
            return await run_in_threadpool(
                services(request).auditor.verify_tool,
                tool_id,
                force_live=live,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.post("/api/auditor/monitor/{tool_id}")
    async def auditor_monitor(
        tool_id: str,
        request: Request,
        live: bool = Query(default=False),
        establish_baseline: bool = Query(default=False),
    ) -> dict[str, Any]:
        try:
            return await run_in_threadpool(
                services(request).auditor.monitor_tool,
                tool_id,
                force_live=live,
                establish_baseline=establish_baseline,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @application.get("/api/trust/{provider_id}")
    async def trust_detail(provider_id: str, request: Request) -> dict[str, Any]:
        state = services(request)
        return {
            "state": state.trust.get(provider_id),
            "history": state.trust.history(provider_id),
            "replay": state.trust.replay(provider_id),
        }

    @application.post("/api/demo/fail-next/{tool_id}")
    async def demo_fail_next(
        tool_id: str,
        request: Request,
        payload: FailNextInput | None = None,
    ) -> dict[str, Any]:
        state = services(request)
        times = payload.times if payload else 1
        if not state.providers.force_failure(tool_id, times=times):
            raise HTTPException(status_code=404, detail="Tool not found")
        return {
            "status": "scheduled",
            "tool_id": tool_id,
            "times": times,
            "message": (
                "The next call will fail. Run the weather/currency demo task to see "
                "circuit-breaker substitution."
            ),
        }

    @application.post("/api/demo/drift/{tool_id}")
    async def demo_drift(tool_id: str, request: Request) -> dict[str, Any]:
        state = services(request)
        alert = state.auditor.inject_drift(
            tool_id, reason="Injected drift: response no longer matches the mapped schema."
        )
        if alert is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        provider = state.graph.get(tool_id)
        if provider and state.settings.use_circuit_breaker:
            state.breakers.trip(
                state.breakers.link_key("client", provider.provider_id),
                f"drift alert {alert.alert_id}",
            )
        return {"status": "drift_injected", "alert": alert.model_dump(mode="json")}

    @application.post("/api/demo/trip/{tool_id}")
    async def demo_trip(tool_id: str, request: Request) -> dict[str, Any]:
        state = services(request)
        tool = state.graph.get(tool_id)
        if tool is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        state.breakers.trip(
            state.breakers.link_key("client", tool.provider_id),
            "Manual trip from the monitoring panel.",
        )
        return {"status": "breaker_open", "tool_id": tool_id}

    @application.post("/api/demo/reset")
    async def demo_reset(request: Request) -> dict[str, Any]:
        services(request).reset_demo()
        return {"status": "reset", "message": "Trust, breakers, drift alerts and demo overrides cleared."}

    @application.post("/api/documents")
    async def upload_document(request: Request, file: UploadFile = File(...)) -> dict[str, Any]:
        state = services(request)
        data = await file.read()
        if len(data) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Document exceeds the 10 MB limit")
        try:
            info = state.providers.document_store.add_document(
                file.filename or "uploaded.txt", data
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"document": info.model_dump(mode="json"), "documents": state.providers.document_store.list()}

    @application.get("/api/documents")
    async def list_documents(request: Request) -> dict[str, Any]:
        return {"documents": services(request).providers.document_store.list()}

    @application.get("/api/documents/{document_id}")
    async def get_document(document_id: str, request: Request) -> dict[str, Any]:
        document = services(request).providers.document_store.get(document_id)
        if document is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return {
            "document": {
                "document_id": document["document_id"],
                "name": document["name"],
                "size_bytes": document["size_bytes"],
                "text_chars": len(document["text"]),
                "created_at": document["created_at"],
                "text": document["text"],
            }
        }

    @application.delete("/api/documents/{document_id}")
    async def delete_document(document_id: str, request: Request) -> dict[str, Any]:
        deleted = services(request).providers.document_store.delete(document_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"deleted": True, "document_id": document_id}

    @application.post("/api/corrections")
    async def submit_correction(payload: CorrectionRequest, request: Request) -> dict[str, Any]:
        state = services(request)
        correction = state.mapper.submit_correction(payload, correlation_id=new_id("req"))
        return correction.model_dump(mode="json")

    @application.post("/api/listings")
    async def submit_listing(payload: ListingIngestRequest, request: Request) -> dict[str, Any]:
        state = services(request)
        mapped = state.mapper.submit_listing(payload, correlation_id=new_id("req"))
        return mapped.model_dump(mode="json")

    @application.get("/api/staged")
    async def staged(request: Request) -> dict[str, Any]:
        return services(request).mapper.staged()

    @application.post("/api/baselines/{name}")
    async def run_baseline(
        name: str,
        payload: TaskInput,
        request: Request,
    ) -> dict[str, Any]:
        state = services(request)
        if name == "b1":
            result = await state.b1.run(payload.task)
        elif name == "b2":
            result = await state.b2.run(payload.task)
        else:
            raise HTTPException(status_code=404, detail="Baseline must be b1 or b2")
        return {
            "baseline": result.baseline,
            "task": result.task,
            "status": result.status,
            "answer": result.answer,
            "rankings": result.rankings,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    @application.get("/api/evaluations")
    async def evaluations() -> dict[str, Any]:
        reports_dir = BASE_DIR / "reports"
        reports = []
        for path in sorted(reports_dir.glob("*.json")):
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            reports.append({"name": path.stem, "summary": payload})
        return {"reports": reports}

    return application


app = create_app()
