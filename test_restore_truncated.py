import sqlite3
import json
import re
from bs4 import BeautifulSoup

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
# Fetch 50 jobs with history
rows = c.execute("""
    SELECT job_id, job_json, raw_html 
    FROM jobs 
    WHERE raw_html IS NOT NULL AND length(raw_html) > 500
    LIMIT 200
""").fetchall()
conn.close()

recovered = 0
total_checked = 0

for jid, jj, raw_html in rows:
    d = json.loads(jj)
    hist = d.get("client_recent_history") or []
    for h in hist:
        fb = (h.get("feedback") or "").strip()
        if fb.endswith("...") or fb.endswith("…"):
            total_checked += 1
            prefix = fb.rstrip(".…").strip()
            # If prefix is at least 25 chars, search raw_html
            if len(prefix) >= 25:
                # Search for prefix in raw_html
                pos = raw_html.find(prefix)
                if pos != -1:
                    # Find end of string in JSON / HTML
                    # In Nuxt JSON or HTML, strings are inside quotes or tags
                    after = raw_html[pos:pos+1000]
                    # Check if inside JSON string (terminated by ")
                    m = re.match(r'^([^"]+)"', after)
                    if m:
                        full_str = m.group(1).replace(r'\"', '"').replace(r'\n', '\n')
                        if len(full_str) > len(fb):
                            recovered += 1
                            # print(f"Recovered: {fb[:40]}... -> {full_str[-40:]}")

print(f"Checked {total_checked} truncated reviews: successfully restored {recovered} ({recovered/max(1, total_checked)*100:.1f}%) directly from raw_html!")
