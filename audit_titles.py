import sqlite3
import json
import os
import re
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
rows = c.execute('SELECT job_id, job_json, length(raw_html) FROM jobs').fetchall()
conn.close()

raw_html_files = set(os.listdir('output/raw_html'))

print(f"Total jobs in DB: {len(rows)}")

title_issues = []
can_fix_from_html = 0
can_fix_from_slug = 0

for jid, jj_str, hlen in rows:
    d = json.loads(jj_str)
    title = (d.get('job_title') or d.get('title') or '').strip()
    url = d.get('job_url') or ''
    
    # Check if title looks truncated or suspect
    is_suspect = False
    if title.endswith('...') or title.endswith('…') or len(title) <= 5:
        is_suspect = True
    elif title == "Untitled Job":
        is_suspect = True
    
    # Check if HTML is available
    safe = jid.replace('~', '').replace('/', '_').replace(':', '_')
    has_html = (hlen and hlen > 0) or f"{safe}.html" in raw_html_files or f"{jid}.html" in raw_html_files
    
    if is_suspect:
        title_issues.append((jid, title, url, has_html))

print(f"Jobs with obviously truncated/suspect titles: {len(title_issues)}")
for item in title_issues[:10]:
    print("  ", item)
