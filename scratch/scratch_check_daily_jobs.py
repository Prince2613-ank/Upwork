import sqlite3
import json

conn = sqlite3.connect("output/database_daily_2026-10-16.db")
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs ORDER BY rowid DESC LIMIT 15").fetchall()
conn.close()

print(f"Total jobs in today's daily DB: {len(rows)}")
for jid, js in rows:
    d = json.loads(js)
    print(f"ID: {jid} | RAW: {d.get('posted_raw')} | POSTED_AT: {d.get('posted_at')} | TITLE: {d.get('job_title')[:35]}")
