content = open('tests/test_core_extra2.py', 'r').read()
content = content.replace(
    'breaker = registry.get("test-provider")\n    breaker.trip()',
    'registry.trip("test-provider")'
)
open('tests/test_core_extra2.py', 'w').write(content)
print('Fixed')