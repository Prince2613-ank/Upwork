import sqlite3, json, sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE job_json LIKE '%client_recent_history%' LIMIT 50")
rows = cur.fetchall()

found = 0
for jid, raw_j, raw_html in rows:
    d = json.loads(raw_j)
    hist = d.get("client_recent_history") or []
    valid_hist = [h for h in hist if h.get("feedback")]
    if valid_hist:
        print(f"============================================================")
        print(f"Job ID: {jid} | History items with feedback: {len(valid_hist)}")
        for h in valid_hist[:3]:
            print(f"  • Title: {h.get('job_title')}")
            print(f"    Rating: {h.get('rating')} | Amount: {h.get('amount')}")
            print(f"    Freelancer: {h.get('freelancer_name')}")
            print(f"    Feedback: {h.get('feedback')}")
        found += 1
        if found >= 3:
            break
