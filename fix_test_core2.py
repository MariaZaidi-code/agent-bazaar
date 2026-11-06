content = open('tests/test_core_extra2.py', 'r').read()
# Add CircuitBreakerRegistry import if not present
if 'from app.core.circuit_breaker import CircuitBreakerRegistry' not in content:
    content = content.replace(
        'from app.core.cache import Cache',
        'from app.core.cache import Cache\nfrom app.core.circuit_breaker import CircuitBreakerRegistry'
    )
# Fix request metrics assertion
content = content.replace(
    'assert snapshot["endpoints"]["GET /api/tools"] == 2',
    'assert snapshot["endpoints"]["GET /api/tools"]["count"] == 2'
)
open('tests/test_core_extra2.py', 'w').write(content)
print('Fixed')