import os
import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta

sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"

now_dt = datetime.now()
tuesday_str = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
monday_str = (now_dt - timedelta(days=2)).strftime("%Y-%m-%d")

print(f"Initializing clean scraping session for Tuesday ({tuesday_str}) & Monday ({monday_str})...")

schema = """CREATE TABLE IF NOT EXISTS jobs (
    job_id   TEXT PRIMARY KEY,
    job_json TEXT,
    raw_html TEXT,
    saved_at TEXT DEFAULT (datetime('now'))
);"""

dbs_to_clean = [
    OUTPUT_DIR / "database_today.db",
    OUTPUT_DIR / "database_yesterday.db",
    OUTPUT_DIR / f"database_daily_{tuesday_str}.db",
    OUTPUT_DIR / f"database_daily_{monday_str}.db",
    OUTPUT_DIR / f"database_weekend_{monday_str}_to_{tuesday_str}.db",
    OUTPUT_DIR / f"database_daily_{monday_str}_to_{tuesday_str}.db"
]

for db_path in dbs_to_clean:
    try:
        conn = sqlite3.connect(db_path, timeout=10)
        conn.execute("DROP TABLE IF EXISTS jobs")
        conn.execute(schema)
        conn.commit()
        cnt = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        conn.close()
        print(f"  ✓ Initialized {db_path.name}: {cnt} rows")
    except Exception as e:
        print(f"  ✗ Error {db_path.name}: {e}")

session_file = OUTPUT_DIR / "daily_session.json"
session_data = {
    "session_calendar_date": now_dt.strftime("%Y-%m-%d"),
    "target_dates": [tuesday_str, monday_str],
    "target_date": tuesday_str,
    "active_db": f"database_daily_{tuesday_str}.db",
    "created_at": now_dt.isoformat()
}
with open(session_file, "w", encoding="utf-8") as f:
    json.dump(session_data, f, indent=2)

print("  ✓ Updated daily_session.json successfully.")
