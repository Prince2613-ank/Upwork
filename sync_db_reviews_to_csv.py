import sqlite3
import json
import csv
from pathlib import Path

db_path = Path("output/database_14days.db")
csv_path = Path("output/client_history.csv")

# 1. Read existing parent_job_ids in client_history.csv
existing_pairs = set()
if csv_path.exists():
    with open(csv_path, "r", encoding="utf-8-sig", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            pid = (r.get("parent_job_id") or "").strip()
            ht = (r.get("history_job_title") or "").strip()
            if pid and ht:
                existing_pairs.add((pid, ht))

print(f"Existing review records in client_history.csv: {len(existing_pairs):,}")

# 2. Extract from database_14days.db
conn = sqlite3.connect(f"file:{db_path.resolve()}?mode=ro", uri=True, timeout=10)
c = conn.cursor()

new_rows = []
for jid, raw in c.execute("SELECT job_id, job_json FROM jobs"):
    try:
        d = json.loads(raw)
        hist = d.get("client_recent_history") or []
        if len(hist) == 0:
            continue
            
        jtitle = d.get("job_title") or ""
        jurl = d.get("job_url") or ""
        cloc = d.get("client_location") or (d.get("client") or {}).get("location") or ""
        
        for h in hist:
            htitle = h.get("job_title") or h.get("history_job_title") or "Contract Completed"
            if (jid, htitle) in existing_pairs:
                continue
                
            new_rows.append([
                jid,
                jurl,
                jtitle,
                d.get("client_profile_url") or "",
                "",
                cloc,
                htitle,
                h.get("job_url") or "",
                h.get("date") or "",
                h.get("duration") or "",
                h.get("payment_type") or "",
                h.get("amount") or "",
                h.get("rating") or "",
                h.get("freelancer_name") or "",
                h.get("feedback") or "",
                str(h.get("feedback_full", True))
            ])
            existing_pairs.add((jid, htitle))
    except Exception:
        pass

conn.close()

if new_rows:
    print(f"Appending {len(new_rows):,} newly verified review rows to {csv_path}...")
    with open(csv_path, "a", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerows(new_rows)
    print(f"Successfully appended {len(new_rows):,} rows to {csv_path}!")
else:
    print("All database reviews already mirrored in client_history.csv.")
