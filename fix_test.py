content = open('tests/test_circuit_breaker_extra.py', 'r').read()
content = content.replace(
    'def test_circuit_breaker_create():\n    registry = CircuitBreakerRegistry()\n    breaker = registry.get_or_create("test-provider")\n    assert breaker is not None',
    'def test_circuit_breaker_create():\n    registry = CircuitBreakerRegistry()\n    breaker = registry.get("test-provider")\n    assert breaker is not None'
)
open('tests/test_circuit_breaker_extra.py', 'w').write(content)
print('Fixed')