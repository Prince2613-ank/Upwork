import sqlite3
import json
import csv
from pathlib import Path

db_path = Path("output/database_14days.db")
csv_path = Path("output/jobs_14days.csv")

conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=10)
c = conn.cursor()

headers = [
    "job_id", "job_title", "job_url", "posted_at", "posted_raw",
    "client_location", "payment_verified", "client_total_spent",
    "client_rating", "client_hours_billed", "client_hire_rate",
    "budget", "job_type", "experience_level", "reviews_count"
]

rows = []
for jid, raw in c.execute("SELECT job_id, job_json FROM jobs ORDER BY rowid DESC"):
    try:
        d = json.loads(raw)
        cl = d.get("client") or {}
        job_sec = d.get("job") or {}
        hist = d.get("client_recent_history") or []
        
        row = [
            jid,
            d.get("job_title") or "",
            d.get("job_url") or "",
            d.get("posted_at") or "",
            d.get("posted_raw") or "",
            d.get("client_location") or cl.get("location") or "",
            "Yes" if cl.get("payment_verified") else "No",
            d.get("client_total_spent") or cl.get("total_spent") or "",
            d.get("client_total_feedback") or cl.get("rating") or "",
            cl.get("hours_billed") or "",
            cl.get("hire_rate") or "",
            job_sec.get("budget") or d.get("budget") or "",
            job_sec.get("job_type") or "",
            job_sec.get("experience_level") or "",
            len(hist)
        ]
        rows.append(row)
    except Exception:
        pass

conn.close()

with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(headers)
    writer.writerows(rows)

print(f"Exported {len(rows):,} jobs to {csv_path} successfully!")
