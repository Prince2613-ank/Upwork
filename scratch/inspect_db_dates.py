import sqlite3, json
from collections import Counter

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT job_id, job_json FROM jobs")
rows = cur.fetchall()
print(f"Total rows in database_1week.db: {len(rows)}")

dates = []
raw_posteds = []
for jid, raw_j in rows:
    d = json.loads(raw_j)
    posted = d.get("posted_at") or d.get("posted_raw") or ""
    dates.append(posted[:10])
    raw_posteds.append(d.get("posted_raw", ""))

c = Counter(dates)
print("\nDates in database_1week.db:")
for k, v in sorted(c.items(), reverse=True):
    print(f"  {k}: {v}")

print("\nSample posted_raw strings for 2026-09-29:")
count_shown = 0
for jid, raw_j in rows:
    d = json.loads(raw_j)
    posted = d.get("posted_at") or d.get("posted_raw") or ""
    if posted.startswith("2026-09-29") and count_shown < 10:
        print(f"  ID: {jid} | posted_at: {d.get('posted_at')} | posted_raw: {d.get('posted_raw')}")
        count_shown += 1
