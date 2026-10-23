"""
Export all 9,363 harmonized jobs from database_1week.db to output/jobs_1week.csv
"""

import sqlite3
import json
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_1WEEK = ROOT / "output" / "database_1week.db"
CSV_OUT = ROOT / "output" / "jobs_1week.csv"

conn = sqlite3.connect(str(DB_1WEEK))
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

headers = [
    "job_id", "job_title", "job_url", "job_description", "skills",
    "client_location", "client_payment_verified", "budget", "budget_type",
    "experience_level", "client_rating", "client_total_spent", "client_jobs_posted",
    "client_hire_rate", "client_total_hires", "client_active_hires", "client_hours_billed",
    "client_member_since", "reviews_count", "posted_at", "posted_raw"
]

with open(CSV_OUT, "w", newline="", encoding="utf-8-sig") as f:
    writer = csv.writer(f)
    writer.writerow(headers)

    for jid, jj_str in rows:
        d = json.loads(jj_str)
        job_dict = d.get("job") or {}
        client_dict = d.get("client") or {}

        title = d.get("job_title") or job_dict.get("title") or d.get("title") or ""
        url = d.get("job_url") or f"https://www.upwork.com/jobs/{jid}"
        desc = job_dict.get("description") or d.get("description") or ""
        
        skills = job_dict.get("skills") or d.get("skills") or []
        if isinstance(skills, list):
            skills_str = ", ".join(str(s) for s in skills)
        else:
            skills_str = str(skills)

        loc = client_dict.get("location") or d.get("client_location") or "Unknown"
        pv = "1" if client_dict.get("payment_verified", True) else "0"
        budget = (d.get("budget_min") and f"${d.get('budget_min')}") or job_dict.get("budget") or "Not Specified"
        b_type = d.get("job_type") or "Fixed"
        exp = d.get("experience_level") or "Intermediate"
        rating = client_dict.get("rating") or "N/A"
        spend = client_dict.get("total_spent") or "N/A"
        posted_cnt = client_dict.get("jobs_posted") or "N/A"
        hire_rate = client_dict.get("hire_rate") or "N/A"
        hires = client_dict.get("total_hires") or "N/A"
        active_hires = client_dict.get("active_hires") or "N/A"
        hrs = client_dict.get("hours_billed") or "N/A"
        member_since = client_dict.get("member_since") or "N/A"
        revs = len(d.get("client_recent_history") or [])
        posted_at = d.get("posted_at") or ""
        posted_raw = d.get("posted_raw") or ""

        writer.writerow([
            jid, title, url, desc, skills_str,
            loc, pv, budget, b_type,
            exp, rating, spend, posted_cnt,
            hire_rate, hires, active_hires, hrs,
            member_since, revs, posted_at, posted_raw
        ])

size_mb = CSV_OUT.stat().st_size / (1024 * 1024)
print(f"[EXPORT SUCCESS] {CSV_OUT.resolve()} ({size_mb:.2f} MB, {len(rows):,} rows)")
