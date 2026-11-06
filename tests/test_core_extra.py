from __future__ import annotations

from app.core.circuit_breaker import CircuitBreakerRegistry
from app.core.webhooks import WebhookRegistry
from app.core.versioning import build_version_manifest
from app.config import Settings


def test_webhook_registry():
    registry = WebhookRegistry()
    assert registry is not None


def test_webhook_registry_register():
    registry = WebhookRegistry()
    hook = registry.register("https://example.com/webhook", events=["task.completed"])
    assert hook is not None


def test_webhook_registry_list(tmp_path):
    registry = WebhookRegistry()
    assert registry.list() == []


def test_webhook_registry_dispatch(tmp_path):
    registry = WebhookRegistry()
    results = registry.dispatch("task.completed", {"task_id": "test"})
    assert isinstance(results, list)


def test_version_manifest(tmp_path):
    from pathlib import Path
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    manifest = build_version_manifest(settings, {}, {})
    assert manifest is not None


def test_settings_defaults(tmp_path):
    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")
    assert settings is not None
    assert settings.offline_mode is True
    assert settings.rate_limit_enabled is True

