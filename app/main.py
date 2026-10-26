from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import BASE_DIR, Settings
from app.schemas import (
    CorrectionRequest,
    HealthResponse,
    ListingIngestRequest,
    TaskResult,
    new_id,
)
from app.services import AppServices, build_services

WEB_DIR = Path(__file__).resolve().parent / "web"
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


class TaskInput(BaseModel):
    task: str = Field(min_length=3, max_length=1500)


class FailNextInput(BaseModel):
    times: int = Field(default=1, ge=1, le=10)


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.services = build_services(settings)
        yield

    application = FastAPI(
        title="Agent Bazaar",
        version=__version__,
        description="Ontology- and knowledge-graph-driven agent marketplace.",
        lifespan=lifespan,
    )
    application.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    def services(request: Request) -> AppServices:
        return request.app.state.services

    @application.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={"version": __version__},
        )

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
            payload.append(data)
        return {"tools": payload, "count": len(payload)}

    @application.post("/api/tasks", response_model=TaskResult)
    async def run_task(payload: TaskInput, request: Request) -> TaskResult:
        state = services(request)
        return await state.client.run(payload.task)

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
