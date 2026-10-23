import sqlite3, json

conn = sqlite3.connect('file:output/database_14days.db?mode=ro', uri=True)
c = conn.cursor()
cnt = c.execute("SELECT COUNT(*) FROM jobs WHERE job_json LIKE '%2026-09-28%'").fetchone()[0]
print('Total matches for 2026-09-28 in database_14days.db:', cnt)

# Check if there are jobs with posted_raw mentioning 7 days ago or 8 days ago
cnt_days = 0
for (r,) in c.execute("SELECT job_json FROM jobs"):
    d = json.loads(r)
    raw = str(d.get('posted_raw') or '').lower()
    if '7 days ago' in raw or '8 days ago' in raw:
        cnt_days += 1
print('Jobs with 7 or 8 days ago:', cnt_days)
conn.close()
