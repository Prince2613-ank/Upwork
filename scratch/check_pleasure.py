import sqlite3, json, sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT job_id, job_json FROM jobs")

for jid, raw_j in cur.fetchall()[:100]:
    d = json.loads(raw_j)
    for h in (d.get("client_recent_history") or []):
        fb = h.get("feedback") or ""
        fl = h.get("freelancer_name") or ""
        if "pleasure working with him" in fb.lower() or "pleasure working with her" in fb.lower():
            print(f"FL: {fl} | Text: {fb}")
