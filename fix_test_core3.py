content = open('tests/test_core_extra2.py', 'r').read()

# Add CircuitBreakerRegistry import
if 'from app.core.circuit_breaker import CircuitBreakerRegistry' not in content:
    content = content.replace(
        'from app.core.cache import Cache',
        'from app.core.cache import Cache\nfrom app.core.circuit_breaker import CircuitBreakerRegistry'
    )

# Fix scheduler test - add registry definition
content = content.replace(
    'def test_scheduler_start_stop(tmp_path):\n    from app.core.scheduler import BackgroundScheduler\n    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")',
    'def test_scheduler_start_stop(tmp_path):\n    from app.core.scheduler import BackgroundScheduler\n    from app.core.webhooks import WebhookRegistry\n    registry = WebhookRegistry()\n    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")'
)

# Fix version_manifest test - add Settings import if missing
content = content.replace(
    'def test_version_manifest(tmp_path):\n    from app.core.versioning import build_version_manifest\n    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")',
    'def test_version_manifest(tmp_path):\n    from app.core.versioning import build_version_manifest\n    from app.config import Settings\n    settings = Settings(offline_mode=True, runtime_dir=tmp_path / "runtime")'
)

open('tests/test_core_extra2.py', 'w').write(content)
print('Fixed')