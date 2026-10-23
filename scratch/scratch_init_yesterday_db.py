import sqlite3
import json
import shutil

conn_master = sqlite3.connect("output/database.db")
c_master = conn_master.cursor()

conn_yest = sqlite3.connect("output/database_daily_2026-10-15.db")
conn_yest.execute("PRAGMA journal_mode=WAL")
conn_yest.execute("""CREATE TABLE IF NOT EXISTS jobs (
    job_id   TEXT PRIMARY KEY,
    job_json TEXT,
    raw_html TEXT,
    saved_at TEXT DEFAULT (datetime('now'))
)""")
c_yest = conn_yest.cursor()

count = 0
for jid, js in c_master.execute("SELECT job_id, job_json FROM jobs"):
    try:
        d = json.loads(js)
        dt = (d.get("posted_at") or "")[:10]
        raw = d.get("posted_raw", "")
        if dt == "2026-10-15" or "yesterday" in raw.lower():
            c_yest.execute("INSERT OR REPLACE INTO jobs (job_id, job_json) VALUES (?, ?)", (jid, js))
            count += 1
    except Exception:
        pass

conn_yest.commit()
conn_yest.close()
conn_master.close()

shutil.copyfile("output/database_daily_2026-10-15.db", "output/database_yesterday.db")
shutil.copyfile("output/database_daily_2026-10-15.db", "output/database_today.db")
print(f"Populated output/database_daily_2026-10-15.db and mirrors with {count:,} jobs from yesterday (2026-10-15)!")
