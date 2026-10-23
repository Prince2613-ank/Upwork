import sqlite3, json

conn = sqlite3.connect('output/database_today.db')
rows = conn.execute('SELECT job_json FROM jobs').fetchall()

count = 0
for jj, in rows:
    d = json.loads(jj)
    revs = d.get('client_recent_history') or (d.get('client') or {}).get('recent_history') or []
    if len(revs) >= 3:
        client = d.get('client') or {}
        print("="*60)
        print("Job Title:", d.get('job_title'))
        print(f"Client Rating: {client.get('rating')}, Total Reviews count: {client.get('reviews_count') or client.get('feedback_count')}")
        print(f"Number of Reviews Extracted on Page: {len(revs)}")
        for i, r in enumerate(revs):
            print(f"  [{i+1}] Title: {r.get('job_title')}")
            print(f"      Rating: {r.get('rating')} | Spend: {r.get('amount')} | Dates: {r.get('dates')}")
            print(f"      Feedback: {r.get('feedback')}")
        count += 1
        if count >= 2:
            break
