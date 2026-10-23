import sqlite3
import json
from pathlib import Path

db_path = Path("output/database_1week.db")
conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
cur = conn.cursor()

cur.execute("""
    SELECT job_id, saved_at, job_json, length(raw_html) 
    FROM jobs 
    ORDER BY rowid DESC 
    LIMIT 6
""")

rows = cur.fetchall()
conn.close()

print(f"=== DEEP INSPECTION OF LATEST 6 SAVED JOBS ===")
for jid, saved_at, raw_json, html_len in rows:
    data = json.loads(raw_json)
    print("\n------------------------------------------------------------")
    print(f"Job ID: {jid} | Saved At: {saved_at} | Raw HTML Size: {html_len:,} bytes")
    print(f"Title: {data.get('job_title')}")
    print(f"URL: {data.get('job_url')}")
    print(f"Client Location: {data.get('client_location') or (data.get('client') or {}).get('location')}")
    print(f"Client Rating: {data.get('client_rating') or (data.get('client') or {}).get('rating')}")
    print(f"Client Total Spent: {data.get('client_total_spent') or (data.get('client') or {}).get('total_spent')}")
    print(f"Client Hires/Jobs: {data.get('client_total_hires') or (data.get('client') or {}).get('hires')} / {data.get('client_total_jobs') or (data.get('client') or {}).get('jobs')}")
    print(f"Job Type / Payment: {data.get('job_type') or data.get('payment_type')} | Budget: {data.get('budget')} | Hourly: {data.get('hourly_rate')}")
    print(f"Skills: {data.get('skills') or data.get('skills_list')}")
    desc = data.get('description') or data.get('job_description') or ''
    print(f"Description length: {len(desc)} chars | Preview: {desc[:120]}...")
    
    reviews = data.get('client_recent_history') or []
    print(f"Client History Reviews: {len(reviews)} reviews")
    if reviews:
        for idx, r in enumerate(reviews[:2], 1):
            print(f"  [Review {idx}] Title: {r.get('job_title') or r.get('history_job_title')} | Rating: {r.get('rating')} | Amount: {r.get('amount')}")
            print(f"               Freelancer: {r.get('freelancer_name')} | Feedback: {str(r.get('feedback'))[:80]}...")
