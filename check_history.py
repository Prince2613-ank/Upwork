import sqlite3
import json
import csv
from pathlib import Path

db_path = Path("output/database.db")
csv_path = Path("output/client_history.csv")

conn = sqlite3.connect(db_path)
c = conn.cursor()

c.execute("SELECT COUNT(*) FROM jobs")
total_jobs = c.fetchone()[0]
print(f"Total jobs in SQLite: {total_jobs}")

# Inspect the 8 most recently collected jobs
c.execute("SELECT rowid, job_id, job_json FROM jobs ORDER BY rowid DESC LIMIT 8")
rows = c.fetchall()

print("\n" + "="*75)
print("  RECENTLY COLLECTED JOBS & CLIENT HISTORY AUDIT (LATEST RECORDS)")
print("="*75)

for rowid, jid, jjson in rows:
    data = json.loads(jjson)
    title = data.get("job_title") or (data.get("job") or {}).get("title") or "N/A"
    client_loc = data.get("client_location") or "N/A"
    client_spend = data.get("client_total_spent") or (data.get("client") or {}).get("total_spent") or "N/A"
    history = data.get("client_recent_history") or []
    
    print(f"\n[Job #{rowid}] {title[:60]}")
    print(f"  URL: https://www.upwork.com/jobs/{jid}")
    print(f"  Client Location: {client_loc} | Total Spent: {client_spend}")
    print(f"  Client History Items Extracted & Saved: {len(history)}")
    
    for i, h in enumerate(history[:3], 1):
        htitle = h.get("job_title") or h.get("history_job_title") or "N/A"
        hdate = h.get("date") or "N/A"
        hamount = h.get("amount") or "N/A"
        hrating = h.get("rating") or "N/A"
        hfeedback = (h.get("feedback") or "")[:70]
        print(f"    Item {i}: '{htitle[:45]}' | Date: {hdate.replace(chr(10), ' ')} | Amount: {hamount} | Rating: {hrating}")
        if hfeedback:
            print(f"      Feedback: \"{hfeedback}...\"")
    if len(history) > 3:
        print(f"    ... and {len(history) - 3} more history records saved for this job.")

# Check client_history.csv
if csv_path.exists():
    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        sample_rows = []
        count = 0
        for r in reader:
            count += 1
            if count > 1:
                sample_rows.append(r)
            if len(sample_rows) > 5:
                sample_rows.pop(0)
    print(f"\n[OK] client_history.csv: {count:,} total client history rows saved.")
    print("Latest 3 CSV rows:")
    for r in sample_rows[-3:]:
        print(f"  -> Parent Job: {r.get('parent_job_title', '')[:30]} | Past Work: {r.get('history_job_title', '')[:30]} | Paid: {r.get('amount')} | Date: {r.get('date')}")
