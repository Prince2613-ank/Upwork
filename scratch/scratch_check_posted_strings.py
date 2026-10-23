import sqlite3
import json
from collections import Counter

conn = sqlite3.connect("output/database_daily_2026-10-15.db")
c = conn.cursor()
rows = c.execute("SELECT job_json FROM jobs").fetchall()
conn.close()

raw_strings = Counter()
for (js,) in rows:
    d = json.loads(js)
    raw_strings[d.get("posted_raw", "")] += 1

print(f"Total jobs in DB: {len(rows)}")
print("Posted strings in yesterday DB:")
for s, cnt in raw_strings.most_common(15):
    print(f"  '{s}': {cnt} jobs")
