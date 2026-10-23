import sqlite3
import json
import re
from bs4 import BeautifulSoup

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()

# Find 5 jobs where a review ends with '...' and check raw_html
rows = c.execute("""
    SELECT job_id, job_json, raw_html 
    FROM jobs 
    WHERE raw_html IS NOT NULL AND length(raw_html) > 1000
    LIMIT 200
""").fetchall()
conn.close()

found = 0
for jid, jj, raw_html in rows:
    d = json.loads(jj)
    hist = d.get("client_recent_history") or []
    for h in hist:
        fb = h.get("feedback") or ""
        if fb.endswith("...") or fb.endswith("…"):
            found += 1
            print(f"\n--- Example {found}: Job {jid} ---")
            print("Current feedback in DB:", repr(fb[:120]))
            print("Freelancer name:", h.get("freelancer_name"))
            
            # Check raw_html for more text
            soup = BeautifulSoup(raw_html, "html.parser")
            # Search for the beginning of this feedback
            clean_snippet = fb[:40]
            matches = [t for t in soup.find_all(text=True) if clean_snippet in t]
            print(f"Matches in raw_html for snippet: {len(matches)}")
            for m in matches[:2]:
                print("  Parent tag:", m.parent.name, m.parent.attrs)
                print("  Full text in HTML:", repr(m.parent.get_text(strip=True)[:200]))
            break
    if found >= 3:
        break

if found == 0:
    print("No truncated feedback found in sample.")
