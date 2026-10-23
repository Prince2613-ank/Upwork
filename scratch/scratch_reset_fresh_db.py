import sqlite3
from pathlib import Path

out = Path("output")
dbs = ["database_daily_2026-10-15.db", "database_yesterday.db", "database_today.db"]
for d in dbs:
    p = out / d
    conn = sqlite3.connect(p)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("DROP TABLE IF EXISTS jobs")
    conn.execute("""CREATE TABLE jobs (
        job_id   TEXT PRIMARY KEY,
        job_json TEXT,
        raw_html TEXT,
        saved_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()
    conn.close()
    print(f"Fresh database initialized: {p.name} (0 jobs)")
