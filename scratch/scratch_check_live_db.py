import sqlite3
import json

conn = sqlite3.connect("output/database_daily_2026-10-15.db")
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json, saved_at FROM jobs ORDER BY rowid DESC").fetchall()
conn.close()

print(f"Total jobs saved in fresh yesterday DB right now: {len(rows)}")
for jid, js, sat in rows[:15]:
    d = json.loads(js)
    title = (d.get("job_title") or "")[:35]
    posted = d.get("posted_raw") or d.get("posted_at") or ""
    revs = len(d.get("client_recent_history") or [])
    desc_len = len((d.get("job") or {}).get("description") or d.get("description") or "")
    print(f"  [{sat}] {jid} | {title} | {posted} | Desc: {desc_len} chars | Revs: {revs}")
