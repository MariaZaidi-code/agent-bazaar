import sqlite3
for db in ['data/runtime/trust.db', 'data/runtime/traces.db', 'data/runtime/documents.db']:
    print(f'=== {db} ===')
    conn = sqlite3.connect(str(db))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    for t in tables:
        print(f'  Table: {t[0]}')
        cursor2 = conn.cursor()
        cursor2.execute(f'PRAGMA table_info({t[0]})')
        for col in cursor2.fetchall():
            print(f'    {col}')
    conn.close()