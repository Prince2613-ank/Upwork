import sqlite3
import json
import re
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_daily_2026-10-20.db")
rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs").fetchall()
conn.close()

print(f"Total jobs currently in database_daily_2026-10-20.db: {len(rows)}")

paginated_jobs = []
for jid, jj, raw in rows:
    # Check if raw_html has pagination in client history
    soup = BeautifulSoup(raw, "html.parser")
    # Search for pagination
    pags = soup.select(".air3-pagination, ul.pagination, [data-test='pagination'], [aria-label*='pagination']")
    m = re.search(r"Client's recent history\s*\((\d+)\)", raw)
    total_hist = int(m.group(1)) if m else 0
    
    d = json.loads(jj)
    saved_hist = len(d.get("client_recent_history") or [])
    
    if total_hist > 5 or pags:
        paginated_jobs.append({
            "jid": jid,
            "title": d.get("job_title"),
            "total_hist": total_hist,
            "saved_hist": saved_hist,
            "has_pags": len(pags) > 0
        })

print(f"Jobs where Client History header > 5: {len(paginated_jobs)}")
for pj in paginated_jobs[:10]:
    print(f"  {pj['jid']}: total={pj['total_hist']}, saved={pj['saved_hist']}, has_pagination={pj['has_pags']} | {pj['title'][:40]}")
