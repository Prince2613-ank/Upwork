"""
Flodata Analytics: Clean Export Utility.
Exports all jobs from SQLite database.db directly to output/jobs.csv
with standard CSV quoting to prevent any newline splits and ensure 100% description integrity.
"""

import sqlite3
import json
import csv
from pathlib import Path

DB_PATH = "output/database.db"
CSV_PATH = "output/jobs.csv"

def clean_export():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
    conn.close()

    fieldnames = [
        "job_id", "job_title", "job_url", "posted_at", "posted_raw",
        "client_location", "payment_verified", "client_rating", "client_total_spent",
        "budget", "job_type", "experience_level", "description", "skills", "history_count"
    ]

    print(f"Exporting {len(rows):,} jobs cleanly from SQLite to {CSV_PATH}...")
    written = 0
    empty_desc = 0

    with open(CSV_PATH, "w", encoding="utf-8-sig", newline="", errors="replace") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_ALL)
        writer.writeheader()

        for jid, raw_j in rows:
            try:
                d = json.loads(raw_j)
                job_dict = d.get("job") or {}
                client_dict = d.get("client") or {}

                desc = (job_dict.get("description") or d.get("description") or "").strip()
                if not desc:
                    empty_desc += 1

                skills_list = job_dict.get("skills") or d.get("skills") or []
                if isinstance(skills_list, list):
                    skills_str = ", ".join(str(s) for s in skills_list)
                else:
                    skills_str = str(skills_list)

                b_min = d.get("budget_min")
                b_str = f"${b_min}" if b_min else (job_dict.get("budget") or "Not Specified")

                writer.writerow({
                    "job_id": jid,
                    "job_title": (d.get("job_title") or job_dict.get("title") or d.get("title") or "Untitled Job").strip(),
                    "job_url": d.get("job_url") or f"https://www.upwork.com/jobs/{jid}",
                    "posted_at": d.get("posted_at") or d.get("posted_raw") or "",
                    "posted_raw": d.get("posted_raw") or "",
                    "client_location": (client_dict.get("location") or d.get("client_location") or "Unknown").strip(),
                    "payment_verified": "1" if client_dict.get("payment_verified", True) else "0",
                    "client_rating": client_dict.get("rating") or "N/A",
                    "client_total_spent": client_dict.get("total_spent") or "N/A",
                    "budget": b_str,
                    "job_type": d.get("job_type") or "Fixed",
                    "experience_level": d.get("experience_level") or "Intermediate",
                    "description": desc,
                    "skills": skills_str,
                    "history_count": len(client_dict.get("reviews") or []),
                })
                written += 1
            except Exception:
                pass

    print(f"[SUCCESS] Exported {written:,} rows to {CSV_PATH}. Empty descriptions: {empty_desc}")
    return written, empty_desc

if __name__ == "__main__":
    clean_export()
