import os
import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "output"
LOGS_DIR = OUTPUT_DIR / "logs"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# 1. Backup old 1week DB
db_1w = OUTPUT_DIR / "database_1week.db"
backup_db = OUTPUT_DIR / "database_1week_backup_sep27_oct04.db"
if db_1w.exists() and not backup_db.exists():
    shutil.copyfile(db_1w, backup_db)
    print(f"[OK] Backed up previous 1-week database to {backup_db.name}")

# 2. Reset database_1week.db and database_7days.db
for db_file in [OUTPUT_DIR / "database_1week.db", OUTPUT_DIR / "database_7days.db"]:
    conn = sqlite3.connect(db_file)
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
    print(f"[OK] Initialized clean, empty database: {db_file.name} (0 jobs)")

# 3. Clear live feed logs
for lf in LOGS_DIR.glob("live_feed*.jsonl"):
    lf.write_text("", encoding="utf-8")
    print(f"[OK] Cleared log file: {lf.name}")

# 4. Reset jobs_1week.csv & jobs_7days.csv
header = "job_id,job_title,job_url,posted_raw,client_location,budget,experience_level,client_total_spent,client_rating,freelancer_reviews_count,description,skills\n"
for csv_name in ["jobs_1week.csv", "jobs_7days.csv"]:
    csv_file = OUTPUT_DIR / csv_name
    csv_file.write_text(header, encoding="utf-8")
    print(f"[OK] Initialized clean CSV: {csv_name}")

print("\n[SUCCESS] Workspace database and exports completely reset for 7-day window (2026-10-04 to 2026-10-11)!")
