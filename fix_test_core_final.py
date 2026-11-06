content = open('tests/test_core_extra2.py', 'r').read()
# Add CircuitBreakerRegistry import at the top if not present
if 'from app.core.circuit_breaker import CircuitBreakerRegistry' not in content:
    content = content.replace(
        'from app.core.cache import Cache',
        'from app.core.cache import Cache\nfrom app.core.circuit_breaker import CircuitBreakerRegistry'
    )
# Fix version_manifest test
content = content.replace(
    'assert "counts" in manifest["counts"]',
    'assert "concepts" in manifest["counts"]'
)
open('tests/test_core_extra2.py', 'w').write(content)
print('Fixed')