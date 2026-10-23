import sqlite3
import csv
from collector.models.schema import CollectedJob
from collector.storage.csv_export import export_jobs_csv, export_client_history_csv

print("Reading existing job IDs from jobs.csv...")
csv_ids = set()
with open("output/jobs.csv", "r", encoding="utf-8-sig", errors="replace") as f:
    csv_ids = {r["job_id"] for r in csv.DictReader(f) if r.get("job_id")}

conn = sqlite3.connect("output/database.db")
c = conn.cursor()
all_db_ids = [r[0] for r in c.execute("SELECT job_id FROM jobs").fetchall()]

missing_ids = [jid for jid in all_db_ids if jid not in csv_ids]
print(f"Total in DB: {len(all_db_ids)}, Total in CSV: {len(csv_ids)}, Missing: {len(missing_ids)}")

if missing_ids:
    print("Fetching missing jobs from DB...")
    missing_jobs = []
    # Query in batches of 50
    for i in range(0, len(missing_ids), 50):
        batch = missing_ids[i:i+50]
        placeholders = ",".join("?" for _ in batch)
        rows = c.execute(f"SELECT job_json FROM jobs WHERE job_id IN ({placeholders})", batch).fetchall()
        for (raw_j,) in rows:
            try:
                missing_jobs.append(CollectedJob.model_validate_json(raw_j))
            except Exception as e:
                print("Error parsing job:", e)

    print(f"Exporting {len(missing_jobs)} jobs to CSVs...")
    export_jobs_csv(missing_jobs, merge=True)
    export_client_history_csv(missing_jobs, merge=True)

conn.close()

# Verify final count
with open("output/jobs.csv", "r", encoding="utf-8-sig", errors="replace") as f:
    final_count = sum(1 for _ in csv.DictReader(f))
print(f"DONE! Final jobs.csv row count: {final_count}")
