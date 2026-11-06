content = open('tests/test_core_extra2.py', 'r').read()
content = content.replace(
    'assert "counts" in manifest["counts"]',
    'assert "concepts" in manifest["counts"]'
)
open('tests/test_core_extra2.py', 'w').write(content)
print('Fixed')