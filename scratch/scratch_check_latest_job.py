import sqlite3
import json

conn = sqlite3.connect("output/database_daily_2026-10-15.db")
row = conn.execute("SELECT job_id, job_json, raw_html FROM jobs ORDER BY rowid DESC LIMIT 1").fetchone()
conn.close()

jid, jjson, raw = row
d = json.loads(jjson)
print("Latest Job ID:", jid)
print("Title:", d.get("job_title"))
print("Desc Length in JSON:", len(d.get("description") or ""))
print("Raw HTML Length:", len(raw or ""))

with open("scratch/scratch_latest_job.html", "w", encoding="utf-8") as f:
    f.write(raw or "")
print("Saved scratch/scratch_latest_job.html")
