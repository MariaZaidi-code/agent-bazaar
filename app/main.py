from __future__ import annotations

import csv
import hashlib
import hmac
import hmac as _hmac
import io
import json
import secrets
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

import httpx
from fastapi import BackgroundTasks, FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app import __version__
from app.config import BASE_DIR, Settings
from app.core.observability import RequestMetrics
from app.platform import (
    DEMO_USER_ID,
    SESSION_COOKIE,
    SESSION_DAYS,
    WORKSPACE_COOKIE,
    RateLimiter,
    analytics_payload,
    pdf_document,
    task_summary,
    validate_webhook_url,
)
from app.schemas import (
    CorrectionRequest,
    HealthResponse,
    ListingIngestRequest,
    TaskResult,
    ToolSpec,
    new_id,
)
from app.services import AppServices, build_services
from app.discovery import CURATED_APIS, sync_discovered
from app.discovery.api import register_discovery_routes
from app.providers.generic import DISCOVERED_CONFIG, GenericHttpProvider

WEB_DIR = Path(__file__).resolve().parent / "web"
STATIC_DIR = WEB_DIR / "static"
ASSET_VERSION = str(
    int(
        max(
            (
                path.stat().st_mtime
                for path in (
                    STATIC_DIR / name for name in ("styles.css", "premium.css", "platform.css", "app.js", "platform.js")
                )
                if path.exists()
            ),
            default=0,
        )
    )
)
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))


class TaskInput(BaseModel):
    task: str = Field(min_length=3, max_length=1500)
    document_id: str | None = Field(default=None, min_length=1, max_length=80)
    reasoning_mode: Literal["none", "llm", "hybrid"] | None = None


class FailNextInput(BaseModel):
    times: int = Field(default=1, ge=1, le=10)


class AuthInput(BaseModel):
    email: str = Field(min_length=3, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=80)
    workspace_name: str = Field(default="", max_length=80)


class FavoriteInput(BaseModel):
    tool_id: str = Field(min_length=1, max_length=120)
    note: str = Field(default="", max_length=500)
    tags: str = Field(default="", max_length=200)


class SavedTaskInput(BaseModel):
    task_id: str = Field(min_length=1, max_length=120)
    title: str = Field(default="", max_length=300)


class DocumentTagsInput(BaseModel):
    tags: list[str] = Field(default_factory=list)


class WorkflowInput(BaseModel):
    name: str = Field(default="Saved workflow", max_length=120)
    task: str = Field(min_length=3, max_length=1500)
    document_id: str | None = Field(default=None, max_length=80)
    plan: dict[str, Any] = Field(default_factory=dict)


class SettingsInput(BaseModel):
    theme: str | None = None
    offline_mode: bool | None = None
    notifications: bool | None = None
    high_contrast: bool | None = None
    workspace_id: str | None = None


class WorkspaceInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class WebhookInput(BaseModel):
    url: str = Field(min_length=8, max_length=500)
    event: str = Field(default="task.completed", max_length=80)

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("http://", "https://")):
            raise ValueError("url must be http(s)")
        return value


class ScheduleInput(BaseModel):
    task: str = Field(min_length=3, max_length=1500)
    cadence: str = Field(default="daily", max_length=20)


class OverrideInput(BaseModel):
    tool_id: str = Field(min_length=1, max_length=120)
    field_name: str = Field(min_length=1, max_length=80)
    value: str = Field(default="", max_length=500)


class ApiKeyInput(BaseModel):
    provider: str = Field(min_length=1, max_length=80)
    key: str = Field(min_length=1, max_length=500)


class FavoriteTagsInput(BaseModel):
    note: str = Field(default="", max_length=500)
    tags: str = Field(default="", max_length=200)


class NotificationReadInput(BaseModel):
    ids: list[int] = Field(default_factory=list)


class FlagInput(BaseModel):
    enabled: bool = False


class DiscoveryAddInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(min_length=1, max_length=500)
    path: str = Field(default="", max_length=200)
    params: list[str] = Field(default_factory=list)
    capability: str = Field(default="GenericLookup", max_length=80)


def _export_task(result: TaskResult, fmt: str) -> tuple[bytes, str, str]:
    data = result.model_dump(mode="json")
    stem = f"agent-bazaar-{result.task_id}"
    if fmt == "pdf":
        lines = [
            f"Task: {result.task}",
            f"Task ID: {result.task_id}",
            f"Status: {result.status}",
            f"Mode: {result.mode}",
            f"Duration: {result.duration_ms:.0f} ms",
            "",
            "Answer",
            result.answer or "(no answer)",
            "",
            "Plan",
        ]
        if result.plan:
            for index, step in enumerate(result.plan.steps, start=1):
                lines.append(f"{index}. {step.tool_name} ({step.capability}) - {step.status}")
                if step.error:
                    lines.append(f"   Error: {step.error}")
        else:
            lines.append("No plan was recorded.")
        if result.warnings:
            lines.extend(["", "Warnings"])
            lines.extend(f"- {warning}" for warning in result.warnings)
        return pdf_document("Agent Bazaar task report", lines), "application/pdf", f"{stem}.pdf"
    if fmt == "csv":
        buffer = io.StringIO()
        writer = csv.DictWriter(
            buffer,
            fieldnames=[
                "record",
                "task_id",
                "task",
                "status",
                "step",
                "tool",
                "capability",
                "step_status",
                "answer",
                "error",
            ],
        )
        writer.writeheader()
        writer.writerow(
            {
                "record": "task",
                "task_id": result.task_id,
                "task": result.task,
                "status": result.status,
                "answer": result.answer,
                "error": result.error or "",
            }
        )
        if result.plan:
            for index, step in enumerate(result.plan.steps, start=1):
                writer.writerow(
                    {
                        "record": "step",
                        "task_id": result.task_id,
                        "step": index,
                        "tool": step.tool_id,
                        "capability": step.capability,
                        "step_status": step.status,
                        "error": step.error or "",
                    }
                )
        return buffer.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8", f"{stem}.csv"
    if fmt == "md":
        lines = [
            f"# {result.task}",
            "",
            f"- Task ID: `{result.task_id}`",
            f"- Status: **{result.status}**",
            f"- Mode: {result.mode}",
            f"- Duration: {result.duration_ms:.0f} ms",
            "",
            "## Answer",
            "",
            result.answer or "_No answer was recorded._",
            "",
            "## Plan",
            "",
        ]
        if result.plan:
            lines.append("| # | Tool | Capability | Status |")
            lines.append("| --- | --- | --- | --- |")
            for index, step in enumerate(result.plan.steps, start=1):
                lines.append(f"| {index} | {step.tool_name} | {step.capability} | {step.status} |")
        else:
            lines.append("_No plan was recorded._")
        if result.warnings:
            lines.extend(["", "## Warnings", ""])
            lines.extend(f"- {warning}" for warning in result.warnings)
        return (
            ("\n".join(lines) + "\n").encode("utf-8"),
            "text/markdown; charset=utf-8",
            f"{stem}.md",
        )
    payload = json.dumps(data, indent=2, default=str).encode("utf-8")
    return payload, "application/json", f"{stem}.json"


import hashlib
import hmac as _hmac


async def _deliver_webhooks(hooks: list[dict[str, Any]], event: str, payload: dict[str, Any]) -> None:
    body = {"event": event, "data": payload}
    raw = json.dumps(body).encode("utf-8")
    async with httpx.AsyncClient(timeout=5.0) as client:
        for hook in hooks:
            if str(hook.get("event") or "task.completed") not in {event, "*"}:
                continue
            headers = {}
            secret = str(hook.get("secret") or "")
            if secret:
                sig = _hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
                headers["X-Agent-Bazaar-Signature"] = sig
            try:
                await client.post(
                    str(hook["url"]), content=raw, headers={"Content-Type": "application/json", **headers}
                )
            except httpx.HTTPError:
                continue


def create_app(settings: Settings | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(application: FastAPI):
        services = build_services(settings)
        application.state.services = services
        application.state.settings = services.settings
        try:
            await services.start_mcp()
        except Exception:
            pass
        # Register discovery API routes with access to staging registry
        register_discovery_routes(application, services.discovery)
        application.state.rate_limiter = RateLimiter(services.settings.rate_limit_per_minute)
        yield

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
    application.state.metrics = RequestMetrics()
    application.state.settings = settings

    # Register discovery API routes (injected after lifespan for access to services)
    # Routes are registered in the lifespan after services are built

    @application.middleware("http")
    async def platform_guard(request: Request, call_next):
        started = time.perf_counter()
        # CSRF validation for mutating API requests
        _settings = getattr(request.app.state, "settings", None)
        csrf_enabled = getattr(_settings, "csrf_enabled", True)
        if (
            csrf_enabled
            and request.url.path.startswith("/api/")
            and request.method in {"POST", "PUT", "PATCH", "DELETE"}
            and request.url.path not in {"/api/auth/login", "/api/auth/register"}
        ):
            csrf_cookie = request.cookies.get("csrf_token")
            csrf_header = request.headers.get("X-CSRF-Token")
            if csrf_cookie and csrf_header and not hmac.compare_digest(csrf_cookie, csrf_header):
                return JSONResponse(status_code=403, content={"detail": "CSRF token mismatch"})
            limiter = getattr(request.app.state, "rate_limiter", None)
            if limiter is not None:
                host = request.client.host if request.client else "local"
                allowed, retry_after = limiter.check(f"{host}:{request.url.path}")
                if not allowed:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "detail": "You are going a little fast. Try again in a moment.",
                            "retry_after": retry_after,
                        },
                        headers={"Retry-After": str(retry_after)},
                    )
        response = await call_next(request)
        # issue CSRF cookie if missing
        if "csrf_token" not in request.cookies:
            token = secrets.token_urlsafe(32)
            response.set_cookie("csrf_token", token, samesite="lax", path="/", secure=request.url.scheme == "https")
        metrics = getattr(request.app.state, "metrics", None)
        if metrics is not None:
            metrics.record(
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
            )
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        if getattr(_settings, "session_cookie_secure", True):
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; "
            "style-src 'self'; img-src 'self' data: https:; "
            "font-src 'self' data:; connect-src 'self'; worker-src 'self'; "
            "manifest-src 'self'; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'",
        )
        return response

    def services(request: Request) -> AppServices:
        return request.app.state.services

    def session_context(request: Request) -> tuple[dict[str, Any], str, bool]:
        state = services(request)
        token = request.cookies.get(SESSION_COOKIE)
        user = state.platform.session_user(token)
        authenticated = user is not None
        if user is None:
            user = state.platform.user(DEMO_USER_ID)
        if user is None:
            raise HTTPException(status_code=500, detail="Demo workspace is unavailable")
        workspace_id = request.cookies.get(WORKSPACE_COOKIE) or state.platform.preferred_workspace(str(user["user_id"]))
        if state.platform.member_role(str(user["user_id"]), workspace_id) == "viewer":
            workspace_id = state.platform.preferred_workspace(str(user["user_id"]))
        return user, workspace_id, authenticated

    def require_admin(user: dict[str, Any], workspace_id: str, state: AppServices) -> None:
        if state.platform.member_role(str(user["user_id"]), workspace_id) != "admin":
            raise HTTPException(status_code=403, detail="Only workspace admins can do that.")

    def attach_session(response: Response, state: AppServices, token: str, request: Request) -> None:
        response.set_cookie(
            SESSION_COOKIE,
            token,
            max_age=SESSION_DAYS * 24 * 60 * 60,
            httponly=True,
            samesite="lax",
            secure=state.settings.session_cookie_secure and request.url.scheme == "https",
            path="/",
        )
        if "csrf_token" not in request.cookies:
            response.set_cookie(
                "csrf_token",
                secrets.token_urlsafe(32),
                samesite="lax",
                path="/",
                secure=state.settings.session_cookie_secure and request.url.scheme == "https",
            )

    def render_page(request: Request, page: str, title: str, active: str | None = None) -> HTMLResponse:
        user, workspace_id, authenticated = session_context(request)
        state = services(request)
        response = templates.TemplateResponse(
            request=request,
            name="index.html",
            context={
                "version": __version__,
                "asset_version": ASSET_VERSION,
                "page": page,
                "active": active or page,
                "page_title": title,
                "user": user,
                "workspace": state.platform.workspace(workspace_id),
                "workspaces": state.platform.workspaces(str(user["user_id"])),
                "authenticated": authenticated,
            },
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @application.get("/", response_class=HTMLResponse)
    async def index(request: Request) -> HTMLResponse:
        return render_page(request, "dashboard", "Ask anything")

    @application.get("/dashboard", response_class=HTMLResponse)
    async def dashboard(request: Request) -> HTMLResponse:
        return render_page(request, "dashboard", "Ask anything")

    @application.get("/marketplace", response_class=HTMLResponse)
    async def marketplace(request: Request) -> HTMLResponse:
        return render_page(request, "marketplace", "Find tools")

    @application.get("/monitor", response_class=HTMLResponse)
    async def monitor(request: Request) -> HTMLResponse:
        return render_page(request, "monitor", "System health")

    @application.get("/library", response_class=HTMLResponse)
    async def library(request: Request) -> HTMLResponse:
        return render_page(request, "library", "Why trust this")

    @application.get("/documents", response_class=HTMLResponse)
    async def documents(request: Request) -> HTMLResponse:
        return render_page(request, "documents", "Your files")

    @application.get("/docs", response_class=HTMLResponse)
    async def documentation(request: Request) -> HTMLResponse:
        return render_page(request, "docs", "Documentation")

    @application.get("/help", response_class=HTMLResponse)
    async def help_page(request: Request) -> HTMLResponse:
        return render_page(request, "help", "Help")

    @application.get("/settings", response_class=HTMLResponse)
    async def settings_page(request: Request) -> HTMLResponse:
        return render_page(request, "settings", "Settings")

    @application.get("/analytics", response_class=HTMLResponse)
    async def analytics_page(request: Request) -> HTMLResponse:
        return render_page(request, "analytics", "Usage analytics")

    @application.get("/admin", response_class=HTMLResponse)
    async def admin_page(request: Request) -> HTMLResponse:
        return render_page(request, "admin", "Admin controls")

    @application.get("/share/{token}", response_class=HTMLResponse)
    async def shared_page(token: str, request: Request) -> HTMLResponse:
        state = services(request)
        task_id = state.platform.shared_task(token)
        if task_id is None:
            raise HTTPException(status_code=404, detail="This share link is no longer available")
        result = state.traces.get_result(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Shared task not found")
        response = templates.TemplateResponse(
            request=request,
            name="share.html",
            context={
                "version": __version__,
                "asset_version": ASSET_VERSION,
                "result": result,
            },
        )
        response.headers["Cache-Control"] = "no-store, max-age=0"
        return response

    @application.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    @application.get("/manifest.webmanifest")
    async def web_manifest() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "manifest.webmanifest",
            media_type="application/manifest+json",
        )

    @application.get("/sw.js")
    async def service_worker() -> FileResponse:
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

    def auth_payload(request: Request, user: dict[str, Any], workspace_id: str) -> dict[str, Any]:
        state = services(request)
        return {
            "authenticated": request.cookies.get(SESSION_COOKIE) is not None
            and state.platform.session_user(request.cookies.get(SESSION_COOKIE)) is not None,
            "user": user,
            "workspace": state.platform.workspace(workspace_id),
            "workspaces": state.platform.workspaces(str(user["user_id"])),
            "settings": state.platform.settings(str(user["user_id"])),
        }

    @application.get("/api/auth/me")
    async def auth_me(request: Request) -> dict[str, Any]:
        user, workspace_id, authenticated = session_context(request)
        payload = auth_payload(request, user, workspace_id)
        payload["authenticated"] = authenticated
        return payload

    @application.post("/api/auth/register")
    async def auth_register(payload: AuthInput, request: Request, response: Response) -> dict[str, Any]:
        state = services(request)
        try:
            state.platform.create_user(payload.email, payload.password, payload.display_name, payload.workspace_name)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        login_token = state.platform.login(payload.email, payload.password)
        if login_token is None:
            raise HTTPException(status_code=400, detail="Account created, but sign-in failed")
        token, signed_in = login_token
        attach_session(response, state, token, request)
        workspace_id = state.platform.preferred_workspace(str(signed_in["user_id"]))
        response.set_cookie(
            WORKSPACE_COOKIE, workspace_id, max_age=SESSION_DAYS * 24 * 60 * 60, samesite="lax", path="/"
        )
        state.platform.audit(str(signed_in["user_id"]), workspace_id, "account.created", str(signed_in["email"]))
        data = auth_payload(request, signed_in, workspace_id)
        data["authenticated"] = True
        return data

    @application.post("/api/auth/login")
    async def auth_login(payload: AuthInput, request: Request, response: Response) -> dict[str, Any]:
        state = services(request)
        login_token = state.platform.login(payload.email, payload.password)
        if login_token is None:
            raise HTTPException(status_code=401, detail="That email and password do not match")
        token, user = login_token
        attach_session(response, state, token, request)
        workspace_id = state.platform.preferred_workspace(str(user["user_id"]))
        response.set_cookie(
            WORKSPACE_COOKIE, workspace_id, max_age=SESSION_DAYS * 24 * 60 * 60, samesite="lax", path="/"
        )
        state.platform.audit(str(user["user_id"]), workspace_id, "account.signed_in", str(user["email"]))
        data = auth_payload(request, user, workspace_id)
        data["authenticated"] = True
        return data

    @application.post("/api/auth/logout")
    async def auth_logout(request: Request, response: Response) -> dict[str, Any]:
        state = services(request)
        token = request.cookies.get(SESSION_COOKIE)
        user = state.platform.session_user(token)
        if user:
            workspace_id = state.platform.preferred_workspace(str(user["user_id"]))
            state.platform.audit(str(user["user_id"]), workspace_id, "account.signed_out")
        state.platform.logout(token)
        response.delete_cookie(SESSION_COOKIE, path="/")
        response.delete_cookie(WORKSPACE_COOKIE, path="/")
        return {"authenticated": False}

    @application.get("/api/platform/settings")
    async def platform_settings(request: Request) -> dict[str, Any]:
        user, _, _ = session_context(request)
        return services(request).platform.settings(str(user["user_id"]))

    @application.put("/api/platform/settings")
    async def update_platform_settings(payload: SettingsInput, request: Request, response: Response) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        values = payload.model_dump(exclude_none=True)
        updated = state.platform.update_settings(str(user["user_id"]), values)
        if values.get("workspace_id"):
            workspace_id = str(updated["workspace_id"])
            response.set_cookie(
                WORKSPACE_COOKIE,
                workspace_id,
                max_age=SESSION_DAYS * 24 * 60 * 60,
                samesite="lax",
                path="/",
            )
        return {
            "settings": updated,
            "workspace": state.platform.workspace(workspace_id),
            "workspaces": state.platform.workspaces(str(user["user_id"])),
        }

    @application.get("/api/workspaces")
    async def list_workspaces(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        return {
            "workspaces": state.platform.workspaces(str(user["user_id"])),
            "active": state.platform.workspace(workspace_id),
        }

    @application.post("/api/workspaces")
    async def create_workspace(payload: WorkspaceInput, request: Request, response: Response) -> dict[str, Any]:
        user, _, _ = session_context(request)
        state = services(request)
        workspace = state.platform.create_workspace(str(user["user_id"]), payload.name)
        state.platform.update_settings(str(user["user_id"]), {"workspace_id": workspace["workspace_id"]})
        response.set_cookie(
            WORKSPACE_COOKIE,
            str(workspace["workspace_id"]),
            max_age=SESSION_DAYS * 24 * 60 * 60,
            samesite="lax",
            path="/",
        )
        return {
            "workspace": workspace,
            "workspaces": state.platform.workspaces(str(user["user_id"])),
        }

    @application.get("/api/favorites")
    async def list_favorites(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return {"favorites": services(request).platform.favorites(str(user["user_id"]), workspace_id)}

    @application.post("/api/favorites")
    async def save_favorite(payload: FavoriteInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        if state.graph.get(payload.tool_id) is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        return state.platform.save_favorite(
            str(user["user_id"]), workspace_id, payload.tool_id, payload.note, payload.tags
        )

    @application.put("/api/favorites/{tool_id}")
    async def update_favorite(tool_id: str, payload: FavoriteTagsInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return services(request).platform.save_favorite(
            str(user["user_id"]), workspace_id, tool_id, payload.note, payload.tags
        )

    @application.delete("/api/favorites/{tool_id}")
    async def delete_favorite(tool_id: str, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        removed = services(request).platform.remove_favorite(str(user["user_id"]), workspace_id, tool_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Saved tool not found")
        return {"deleted": True, "tool_id": tool_id}

    @application.get("/api/saved-tasks")
    async def list_saved_tasks(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return {"saved_tasks": services(request).platform.saved_tasks(str(user["user_id"]), workspace_id)}

    @application.post("/api/saved-tasks")
    async def save_task(payload: SavedTaskInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        result = state.traces.get_result(payload.task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Task not found")
        title = payload.title.strip() or result.task[:120]
        return state.platform.save_task(str(user["user_id"]), workspace_id, payload.task_id, title)

    @application.delete("/api/saved-tasks/{task_id}")
    async def delete_saved_task(task_id: str, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        removed = services(request).platform.remove_saved_task(str(user["user_id"]), workspace_id, task_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Saved task not found")
        return {"deleted": True, "task_id": task_id}

    @application.get("/api/workflows")
    async def list_workflows(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        rows = services(request).platform.workflows(str(user["user_id"]), workspace_id)
        workflows = []
        for row in rows:
            item = dict(row)
            try:
                item["plan"] = json.loads(item.pop("plan_json") or "{}")
            except json.JSONDecodeError:
                item["plan"] = {}
                item.pop("plan_json", None)
            workflows.append(item)
        return {"workflows": workflows}

    @application.post("/api/workflows")
    async def save_workflow(payload: WorkflowInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return services(request).platform.save_workflow(
            str(user["user_id"]),
            workspace_id,
            payload.name,
            payload.task,
            payload.document_id,
            payload.plan,
        )

    @application.delete("/api/workflows/{workflow_id}")
    async def delete_workflow(workflow_id: str, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        removed = services(request).platform.remove_workflow(str(user["user_id"]), workspace_id, workflow_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Workflow not found")
        return {"deleted": True, "workflow_id": workflow_id}

    @application.get("/api/notifications")
    async def list_notifications(request: Request, limit: int = Query(default=30, ge=1, le=100)) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        rows = services(request).platform.notifications(str(user["user_id"]), workspace_id, limit)
        return {
            "notifications": rows,
            "unread": sum(1 for row in rows if row.get("read_at") is None),
        }

    @application.post("/api/notifications/read")
    async def read_notifications(payload: NotificationReadInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        updated = services(request).platform.mark_notifications_read(
            str(user["user_id"]), workspace_id, payload.ids or None
        )
        return {"updated": updated}

    @application.get("/api/audit")
    async def audit_log(request: Request, limit: int = Query(default=50, ge=1, le=200)) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return {"entries": services(request).platform.audit_log(str(user["user_id"]), workspace_id, limit)}

    @application.get("/api/analytics")
    async def analytics(request: Request) -> dict[str, Any]:
        state = services(request)
        rows = state.traces.result_rows(limit=2000)
        return analytics_payload(rows, state.trust.all())

    @application.get("/api/admin/flags")
    async def admin_flags(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        require_admin(user, workspace_id, state)
        return {"flags": state.platform.feature_flags()}

    @application.put("/api/admin/flags/{name}")
    async def update_flag(name: str, payload: FlagInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        require_admin(user, workspace_id, state)
        flag = state.platform.set_feature_flag(name, payload.enabled)
        if flag is None:
            raise HTTPException(status_code=404, detail="Feature flag not found")
        state.platform.audit(str(user["user_id"]), workspace_id, "flag.updated", f"{name}={payload.enabled}")
        return flag

    @application.get("/api/admin/overrides")
    async def admin_overrides(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        require_admin(user, workspace_id, state)
        return {"overrides": state.platform.overrides()}

    @application.put("/api/admin/overrides")
    async def update_override(payload: OverrideInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        require_admin(user, workspace_id, state)
        if state.graph.get(payload.tool_id) is None:
            raise HTTPException(status_code=404, detail="Tool not found")
        result = state.platform.set_override(payload.tool_id, payload.field_name, payload.value)
        state.platform.audit(
            str(user["user_id"]), workspace_id, "provider.override", f"{payload.tool_id}:{payload.field_name}"
        )
        return result

    @application.get("/api/webhooks")
    async def list_webhooks(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return {"webhooks": services(request).platform.webhooks(str(user["user_id"]), workspace_id)}

    @application.post("/api/webhooks")
    async def create_webhook(payload: WebhookInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        try:
            services(request).platform.validate_webhook_url(payload.url)
            return services(request).platform.add_webhook(
                str(user["user_id"]), workspace_id, payload.url, payload.event
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.delete("/api/webhooks/{webhook_id}")
    async def delete_webhook(webhook_id: str, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        removed = services(request).platform.remove_webhook(str(user["user_id"]), workspace_id, webhook_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Webhook not found")
        return {"deleted": True, "webhook_id": webhook_id}

    @application.get("/api/schedules")
    async def list_schedules(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        return {"schedules": services(request).platform.scheduled_runs(str(user["user_id"]), workspace_id)}

    @application.post("/api/schedules")
    async def create_schedule(payload: ScheduleInput, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        try:
            return services(request).platform.add_scheduled_run(
                str(user["user_id"]), workspace_id, payload.task, payload.cadence
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @application.delete("/api/schedules/{schedule_id}")
    async def delete_schedule(schedule_id: str, request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        removed = services(request).platform.remove_scheduled_run(str(user["user_id"]), workspace_id, schedule_id)
        if not removed:
            raise HTTPException(status_code=404, detail="Schedule not found")
        return {"deleted": True, "schedule_id": schedule_id}

    @application.post("/api/schedules/run-due")
    async def run_due_schedules(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        require_admin(user, workspace_id, state)
        results = []
        for schedule in state.platform.due_schedules()[:5]:
            result = await state.client.run(str(schedule["task"]))
            state.platform.mark_schedule_ran(str(schedule["schedule_id"]), str(schedule["cadence"]))
            state.platform.notify(
                str(user["user_id"]),
                workspace_id,
                "Scheduled task finished",
                f"{schedule['task'][:90]} finished with status {result.status}.",
                "schedule",
            )
            results.append({"schedule_id": schedule["schedule_id"], "task_id": result.task_id})
        return {"ran": results}

    @application.get("/api/cache")
    async def cache_status(request: Request) -> dict[str, Any]:
        state = services(request)
        return {"entries": state.cache.count(), "ttl_seconds": state.settings.cache_ttl_seconds}

    @application.delete("/api/cache")
    async def clear_cache(request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        require_admin(user, workspace_id, state)
        cleared = state.cache.clear()
        state.platform.audit(str(user["user_id"]), workspace_id, "cache.cleared", f"{cleared} entries")
        return {"cleared": cleared}

    @application.get("/api/api-keys")
    async def list_api_keys(request: Request) -> dict[str, Any]:
        user, _, _ = session_context(request)
        return {"keys": services(request).platform.api_keys(str(user["user_id"]))}

    @application.post("/api/api-keys")
    async def save_api_key(payload: ApiKeyInput, request: Request) -> dict[str, Any]:
        user, _, _ = session_context(request)
        state = services(request)
        try:
            state.platform.set_api_key(str(user["user_id"]), payload.provider, payload.key)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"keys": state.platform.api_keys(str(user["user_id"]))}

    @application.delete("/api/api-keys/{provider}")
    async def delete_api_key(provider: str, request: Request) -> dict[str, Any]:
        user, _, _ = session_context(request)
        removed = services(request).platform.delete_api_key(str(user["user_id"]), provider)
        if not removed:
            raise HTTPException(status_code=404, detail="Credential not found")
        return {"deleted": True, "provider": provider}

    @application.get("/api/workspace/export")
    async def export_workspace(request: Request) -> Response:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        payload = state.platform.workspace_export(str(user["user_id"]), workspace_id)
        state.platform.audit(str(user["user_id"]), workspace_id, "workspace.exported")
        body = json.dumps(payload, indent=2, default=str).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="agent-bazaar-{workspace_id}.json"'},
        )

    @application.post("/api/workspace/import")
    async def import_workspace(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        user, workspace_id, _ = session_context(request)
        state = services(request)
        result = state.platform.workspace_import(str(user["user_id"]), workspace_id, payload)
        state.platform.audit(str(user["user_id"]), workspace_id, "workspace.imported")
        return result

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

    @application.get("/readyz")
    async def readyz(request: Request) -> JSONResponse:
        state = getattr(request.app.state, "services", None)
        providers = len(state.providers.all()) if state is not None else 0
        ready = state is not None and providers > 0
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "ready": ready,
                "providers": providers,
                "mode": "offline" if state and state.settings.offline_mode else "live",
            },
        )

    @application.get("/metrics")
    async def metrics(request: Request) -> Response:
        state = services(request)
        snapshot = request.app.state.metrics.snapshot()
        lines = [
            "# HELP agent_bazaar_requests_total Total HTTP requests served.",
            "# TYPE agent_bazaar_requests_total counter",
            f"agent_bazaar_requests_total {snapshot['requests']}",
            "# HELP agent_bazaar_request_errors_total Total HTTP 5xx responses.",
            "# TYPE agent_bazaar_request_errors_total counter",
            f"agent_bazaar_request_errors_total {snapshot['errors']}",
            "# HELP agent_bazaar_tools_total Tools loaded in the catalogue.",
            "# TYPE agent_bazaar_tools_total gauge",
            f"agent_bazaar_tools_total {len(state.providers.all())}",
        ]
        for key, value in snapshot["statuses"].items():
            lines.append(f'agent_bazaar_responses_total{{status="{key}"}} {value}')
        for provider in state.providers.all():
            score = state.trust.get(provider.provider_id).get("score", 0.0)
            lines.append(f'agent_bazaar_trust_score{{provider="{provider.provider_id}"}} {float(score):.4f}')
        return Response("\n".join(lines) + "\n", media_type="text/plain; version=0.0.4")

    @application.get("/api/ontology")
    async def ontology(request: Request) -> dict[str, Any]:
        state = services(request)
        return {
            "summary": state.ontology.summary(),
            "concepts": [state.ontology.concept_payload(name) for name in sorted(state.ontology.concepts)],
            "units": [state.ontology.unit_payload(name) for name in sorted(state.ontology.units)],
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
            data["breaker"] = state.breakers.state(state.breakers.link_key("client", tool.provider_id)).value
            data["validation"] = state.providers.validation.get(tool.id, [])
            data["auditor_tool_id"] = state.auditor.catalog_tool_id(tool.id) or ""
            payload.append(data)
        return {"tools": payload, "count": len(payload)}

    @application.get("/api/discovery/candidates")
    async def discovery_candidates(request: Request) -> dict[str, Any]:
        state = services(request)
        installed = {tool.id for tool in state.graph.all()}
        payload = []
        for candidate in CURATED_APIS:
            item = dict(candidate)
            item["installed"] = candidate["id"] in installed
            payload.append(item)
        return {"candidates": payload, "count": len(payload)}

    @application.post("/api/discovery/sync")
    async def discovery_sync(request: Request) -> dict[str, Any]:
        state = services(request)
        added = sync_discovered(state.settings, state.graph, state.providers)
        try:
            state.retriever.rebuild()
        except Exception:
            pass
        return {"added": added, "count": len(added)}

    @application.post("/api/discovery/add")
    async def discovery_add(payload: DiscoveryAddInput, request: Request) -> dict[str, Any]:
        state = services(request)
        tool_id = payload.name.lower().replace(" ", "-")
        config = {
            "base_url": payload.base_url,
            "path": payload.path,
            "params": payload.params,
        }
        DISCOVERED_CONFIG[tool_id] = config
        spec = ToolSpec(
            id=tool_id,
            name=payload.name,
            provider_id="generic",
            description=f"Discovered API: {payload.name}",
            capability=payload.capability,
            tags=["discovered"],
            execution="live",
            is_executable=True,
        )
        state.graph.add(spec)
        provider = GenericHttpProvider(spec, state.settings, state.cache)
        state.providers.register(provider)
        # persist
        try:
            records = json.loads(state.settings.tools_file.read_text(encoding="utf-8"))
            if not any(r.get("id") == tool_id for r in records):
                records.append(spec.model_dump(mode="json"))
                state.settings.tools_file.write_text(json.dumps(records, indent=2), encoding="utf-8")
        except Exception:
            pass
        try:
            state.retriever.rebuild()
        except Exception:
            pass
        return {"added": tool_id, "tool_id": tool_id}

    @application.post("/api/tasks", response_model=TaskResult)
    async def run_task(payload: TaskInput, request: Request, background_tasks: BackgroundTasks) -> TaskResult:
        state = services(request)
        if payload.document_id and state.providers.document_store.get(payload.document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found")
        user, workspace_id, _ = session_context(request)
        result = await state.client.run(
            payload.task,
            document_id=payload.document_id,
            reasoning_mode=payload.reasoning_mode,
        )
        state.platform.audit(str(user["user_id"]), workspace_id, "task.completed", result.task_id)
        if state.platform.settings(str(user["user_id"])).get("notifications", True):
            state.platform.notify(
                str(user["user_id"]),
                workspace_id,
                "Task finished" if result.status == "completed" else "Task needs attention",
                f"{result.task[:100]} - {result.status}",
                "success" if result.status == "completed" else "warning",
            )
        hooks = state.platform.webhooks(str(user["user_id"]), workspace_id, include_secret=True)
        if hooks:
            background_tasks.add_task(
                _deliver_webhooks,
                hooks,
                "task.completed" if result.status == "completed" else "task.failed",
                {
                    "task_id": result.task_id,
                    "task": result.task,
                    "status": result.status,
                    "answer": result.answer,
                },
            )
        return result

    @application.get("/api/tasks/recent")
    async def recent_tasks(
        request: Request,
        limit: int = Query(default=15, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        q: str = Query(default="", max_length=200),
        status: str = Query(default="", max_length=40),
        capability: str = Query(default="", max_length=80),
        date_from: str = Query(default="", max_length=40),
        date_to: str = Query(default="", max_length=40),
    ) -> dict[str, Any]:
        rows = services(request).traces.result_rows(limit=2000)
        query = q.strip().lower()
        summaries = []
        for row in rows:
            item = task_summary(row)
            if query and query not in str(item["task"]).lower() and query not in str(item["task_id"]).lower():
                continue
            if status and item["status"] != status:
                continue
            if capability and capability not in item["capabilities"] and capability not in item["tools"]:
                continue
            created = str(item["created_at"] or "")
            if date_from and created[:10] < date_from:
                continue
            if date_to and created[:10] > date_to:
                continue
            summaries.append(item)
        return {
            "tasks": summaries[offset : offset + limit],
            "total": len(summaries),
            "offset": offset,
            "limit": limit,
        }

    @application.post("/api/tasks/{task_id}/share")
    async def share_task(task_id: str, request: Request) -> dict[str, Any]:
        state = services(request)
        if state.traces.get_result(task_id) is None:
            raise HTTPException(status_code=404, detail="Task not found")
        user, workspace_id, _ = session_context(request)
        token = state.platform.share(task_id)
        state.platform.audit(str(user["user_id"]), workspace_id, "task.shared", task_id)
        base = state.settings.share_base_url or str(request.base_url).rstrip("/")
        return {"token": token, "url": f"{base}/share/{token}"}

    @application.get("/api/tasks/{task_id}/export")
    async def export_task(task_id: str, request: Request, format: str = Query(default="json")) -> Response:
        state = services(request)
        result = state.traces.get_result(task_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Task not found")
        if format not in {"json", "csv", "md", "pdf"}:
            raise HTTPException(status_code=400, detail="Choose json, csv, md or pdf")
        content, media_type, filename = _export_task(result, format)
        return Response(
            content=content,
            media_type=media_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

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
                "The next call will fail. Run the weather/currency demo task to see circuit-breaker substitution."
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
            info = state.providers.document_store.add_document(file.filename or "uploaded.txt", data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"document": info.model_dump(mode="json"), "documents": state.providers.document_store.list()}

    @application.get("/api/documents")
    async def list_documents(request: Request) -> dict[str, Any]:
        return {"documents": services(request).providers.document_store.list()}

    @application.get("/api/documents/search")
    async def search_documents(
        request: Request, q: str = Query(..., min_length=1), top_k: int = Query(5, ge=1, le=50)
    ) -> dict[str, Any]:
        results = services(request).providers.document_store.search_documents(q, top_k)
        return {"query": q, "results": results}

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

    @application.put("/api/documents/{document_id}/tags")
    async def set_document_tags(document_id: str, payload: DocumentTagsInput, request: Request) -> dict[str, Any]:
        store = services(request).providers.document_store
        if not store.set_tags(document_id, payload.tags):
            raise HTTPException(status_code=404, detail="Document not found")
        document = store.get(document_id)
        return {"document": document}

    @application.get("/api/documents/{document_id}/chunks")
    async def get_document_chunks(document_id: str, request: Request) -> dict[str, Any]:
        store = services(request).providers.document_store
        if store.get(document_id) is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return {"chunks": store.get_chunks(document_id)}

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
