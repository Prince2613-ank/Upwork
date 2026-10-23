import sqlite3
import json
import os
import re
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()

# Test first 1000 rows
rows = c.execute('SELECT job_id, job_json, raw_html FROM jobs LIMIT 1000').fetchall()
conn.close()

raw_html_dir = 'output/raw_html'
diff_count = 0
diff_samples = []

for jid, jj_str, db_raw in rows:
    d = json.loads(jj_str)
    cur_title = (d.get('job_title') or d.get('title') or '').strip()
    
    html = db_raw
    if not html:
        safe = jid.replace('~', '').replace('/', '_').replace(':', '_')
        path = os.path.join(raw_html_dir, f"{safe}.html")
        if not os.path.exists(path):
            path = os.path.join(raw_html_dir, f"{jid}.html")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    html = f.read()
            except Exception:
                pass
    
    if not html:
        continue
        
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title using proper selectors
    true_title = ""
    # Try h4 or h1 or title tag
    t_tag = soup.find('title')
    t_text = t_tag.get_text().strip() if t_tag else ""
    if t_text:
        # Upwork title tag format: "Title - Category - Upwork" or "Title - Upwork"
        clean_t = re.split(r'\s+-\s+(?:Marketing|Design|Development|Writing|Admin|Customer|Sales|Accounting|Legal|Engineering|IT|Upwork)', t_text)[0].strip()
        clean_t = re.sub(r'\s*\|\s*Upwork.*$', '', clean_t, flags=re.I).strip()
        if len(clean_t) > 5 and "just a moment" not in clean_t.lower():
            true_title = clean_t
            
    # Also check h4 or h1 in main/header
    h_el = soup.select_one("header h1, header h4, main h1, main h4, [data-test='job-title'], h4.job-title, h1.job-title")
    if h_el and len(h_el.get_text(strip=True)) > 5:
        true_title = h_el.get_text(strip=True)
        
    if true_title and true_title != cur_title:
        diff_count += 1
        if len(diff_samples) < 15:
            diff_samples.append((jid, "DB Title:", cur_title, "HTML Title:", true_title))

print(f"Out of 1000 sampled jobs, {diff_count} had title mismatches!")
for s in diff_samples:
    print(f"Job: {s[0]}")
    print(f"   DB:   {repr(s[2])}")
    print(f"   HTML: {repr(s[4])}")
    print("-" * 50)
