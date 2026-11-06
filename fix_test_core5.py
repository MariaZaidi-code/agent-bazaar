content = open('tests/test_core_extra2.py', 'r').read()
content = content.replace(
    'breaker = registry.get("test-provider")\n    breaker.trip()\n    assert breaker.state == "open"',
    'registry.trip("test-provider")\n    assert registry.state("test-provider") == "open"'
)
open('tests/test_core_extra2.py', 'w').write(content)
print('Fixed')