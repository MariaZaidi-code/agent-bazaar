content = open('tests/test_services_extra.py', 'r').read()
content = content.replace(
    'db_path = str(tmpdir / "trust.db")',
    'db_path = tmpdir / "trust.db"'
)
open('tests/test_services_extra.py', 'w').write(content)
print('Fixed')