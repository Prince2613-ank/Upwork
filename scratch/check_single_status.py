import sqlite3
import json

conn = sqlite3.connect("file:output/database_yesterday.db?mode=ro", uri=True)
row = conn.execute("SELECT job_json FROM jobs WHERE job_id='~022110707014726286055'").fetchone()
if row:
    d = json.loads(row[0])
    for h in d.get("client_recent_history", []):
        fb = h.get("feedback", "")
        print(f"FLAG: {h.get('feedback_full')}, LEN: {len(fb)}, ENDS_WITH_DOTS: {fb.endswith('...')}, FB: {fb[:75]}")
conn.close()
