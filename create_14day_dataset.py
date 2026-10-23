import sqlite3
import json
import csv
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = BASE_DIR / "output"
DB_SRC = OUTPUT_DIR / "database.db"
DB_14D = OUTPUT_DIR / "database_14days.db"
CSV_14D = OUTPUT_DIR / "jobs_14days.csv"

DATE_START = "2026-09-14"
DATE_END = "2026-09-28"

print(f"Reading from {DB_SRC.name} and creating dedicated 14-day database: {DB_14D.name}...")

conn_src = sqlite3.connect(str(DB_SRC), timeout=30)
c_src = conn_src.cursor()
rows = c_src.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn_src.close()

conn_dst = sqlite3.connect(str(DB_14D), timeout=30)
c_dst = conn_dst.cursor()
c_dst.execute("CREATE TABLE IF NOT EXISTS seen_ids (job_id TEXT PRIMARY KEY)")
c_dst.execute("CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, job_json TEXT)")
conn_dst.commit()

count_14d = 0
jobs_for_csv = []

for jid, raw_j in rows:
    try:
        d = json.loads(raw_j)
        posted = d.get("posted_at") or d.get("posted_raw") or ""
        p_date = posted[:10]
        if DATE_START <= p_date <= DATE_END:
            c_dst.execute("INSERT OR REPLACE INTO jobs (job_id, job_json) VALUES (?, ?)", (jid, raw_j))
            c_dst.execute("INSERT OR REPLACE INTO seen_ids (job_id) VALUES (?)", (jid,))
            count_14d += 1
            
            job_dict = d.get("job") or {}
            client_dict = d.get("client") or {}
            jobs_for_csv.append({
                "job_id": jid,
                "job_title": d.get("job_title") or job_dict.get("title") or "",
                "job_url": d.get("job_url") or "",
                "posted_at": posted,
                "posted_raw": d.get("posted_raw") or "",
                "client_location": client_dict.get("location") or d.get("client_location") or "",
                "payment_verified": client_dict.get("payment_verified", True),
                "client_total_spent": client_dict.get("total_spent", "N/A"),
                "client_rating": client_dict.get("rating", "N/A"),
                "budget": (d.get("budget_min") and f"${d.get('budget_min')}") or job_dict.get("budget") or "Not Specified",
                "job_type": d.get("job_type") or "Fixed",
                "experience_level": d.get("experience_level") or "Intermediate",
                "reviews_count": len(d.get("client_recent_history") or [])
            })
    except Exception:
        pass

conn_dst.commit()
conn_dst.close()

# Export dedicated CSV
if jobs_for_csv:
    fieldnames = list(jobs_for_csv[0].keys())
    with open(CSV_14D, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(jobs_for_csv)

print(f"[SUCCESS] Created {DB_14D.name} with {count_14d:,} verified 14-day jobs ({DATE_START} to {DATE_END})")
print(f"[SUCCESS] Created {CSV_14D.name} with {len(jobs_for_csv):,} rows")
