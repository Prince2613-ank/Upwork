import sqlite3
import glob
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

target_jid = "022112658363064905128"

dbs = [
    "output/database_daily_2026-10-20.db",
    "output/database_daily_2026-10-19.db",
    "output/database_daily_2026-10-18.db",
    "output/database_daily_2026-10-17.db",
    "output/database_daily_2026-10-16.db",
    "output/database_daily_2026-10-15.db",
    "output/database.db"
]

for db_path in dbs:
    try:
        conn = sqlite3.connect(db_path)
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if 'jobs' in tables:
            rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE job_id LIKE ?", (f"%{target_jid}%",)).fetchall()
            if rows:
                print(f"Found in {db_path}: {len(rows)} matching job(s)")
                for jid, jj, raw in rows:
                    d = json.loads(jj)
                    hist = d.get("client_recent_history") or []
                    print(f"  Job ID: {jid} | Title: {d.get('job_title')} | Saved reviews: {len(hist)}")
                    for idx, r in enumerate(hist):
                        print(f"    [{idx+1}] {r.get('job_title')} (★{r.get('rating')}) | FL: {r.get('freelancer_name')} | Feedback: {r.get('feedback')[:60] if r.get('feedback') else 'None'}")
                    print(f"  Raw HTML size: {len(raw):,} chars")
    except Exception as e:
        pass
