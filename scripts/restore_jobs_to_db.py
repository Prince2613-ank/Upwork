"""
Restores all complete job records from jobs.csv back into database.db.
"""
import sqlite3
import csv
import json
from collector.models.schema import CollectedJob, JobDetails, ClientSection, ExtractionStatus

print("Checking database and CSV...")
conn = sqlite3.connect("output/database.db", timeout=30)
c = conn.cursor()
existing_ids = set(r[0] for r in c.execute("SELECT job_id FROM jobs").fetchall())
print(f"Existing IDs in database.db: {len(existing_ids)}")

to_insert = []
with open("output/jobs.csv", "r", encoding="utf-8-sig", errors="replace") as f:
    reader = csv.DictReader(f)
    for row in reader:
        jid = row.get("job_id")
        if not jid or jid in existing_ids:
            continue
        
        # Build CollectedJob model
        skills_raw = row.get("skills", "")
        skills_list = [s.strip() for s in skills_raw.split(";") if s.strip()] if ";" in skills_raw else [s.strip() for s in skills_raw.split(",") if s.strip()]
        
        pv_val = row.get("payment_verified", "").lower()
        is_pv = pv_val in ("true", "1", "yes")

        job_details = JobDetails(
            description=row.get("description", ""),
            job_type=row.get("job_type", ""),
            experience_level=row.get("experience_level", ""),
            budget=row.get("budget", ""),
            hourly_min=row.get("hourly_min", ""),
            hourly_max=row.get("hourly_max", ""),
            fixed_price=row.get("fixed_price", ""),
            skills=skills_list,
            proposals=row.get("proposals", ""),
        )

        client_sec = ClientSection(
            location=row.get("client_location", ""),
            payment_verified=is_pv,
            rating=row.get("client_rating", ""),
            total_spent=row.get("client_total_spent", ""),
            jobs_posted=row.get("jobs_posted", ""),
            hire_rate=row.get("hire_rate", ""),
            total_hires=row.get("total_hires", ""),
            active_hires=row.get("active_hires", ""),
            hours_billed=row.get("hours_billed", ""),
            member_since=row.get("member_since", ""),
        )

        job_obj = CollectedJob(
            job_id=jid,
            job_url=row.get("job_url", f"https://www.upwork.com/jobs/{jid}"),
            job_title=row.get("job_title", "Untitled Job"),
            posted_at=row.get("posted_at", ""),
            posted_raw=row.get("posted_raw", ""),
            client_location=row.get("client_location", ""),
            job=job_details,
            client=client_sec,
            extraction_status=ExtractionStatus(
                job_details=True,
                description=bool(row.get("description")),
                about_client=True,
                recent_history=False,
                full_reviews=False,
            )
        )
        to_insert.append((jid, job_obj.model_dump_json()))
        existing_ids.add(jid)

print(f"Inserting {len(to_insert)} restored jobs into database.db...")
if to_insert:
    # Insert in batches of 500
    for i in range(0, len(to_insert), 500):
        batch = to_insert[i:i+500]
        c.executemany("INSERT OR IGNORE INTO jobs (job_id, job_json) VALUES (?, ?)", batch)
        c.executemany("INSERT OR IGNORE INTO claims (job_id) VALUES (?)", [(jid,) for jid, _ in batch])
        c.executemany("INSERT OR IGNORE INTO seen_ids (job_id) VALUES (?)", [(jid,) for jid, _ in batch])
        conn.commit()

c.execute("SELECT count(*) FROM jobs")
final_db_count = c.fetchone()[0]
conn.close()
print(f"RESTORATION COMPLETE! Total jobs in database.db is now: {final_db_count}")
