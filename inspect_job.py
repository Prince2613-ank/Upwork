import sqlite3
import json
from bs4 import BeautifulSoup

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()

job_id = '~022089338363935389527'
c.execute("SELECT job_id, job_json, length(raw_html), raw_html FROM jobs WHERE job_id = ? OR job_id LIKE ? OR job_json LIKE ?", 
          (job_id, f"%{job_id}%", f"%{job_id}%"))
rows = c.fetchall()
print(f"Found {len(rows)} matching rows in jobs table")

for r in rows:
    jid, jjson_str, html_len, raw_html = r
    print(f"Job ID: {jid}, raw_html len: {html_len}")
    try:
        jj = json.loads(jjson_str)
        print("JSON Title:", repr(jj.get('job_title') or jj.get('title')))
        print("JSON Client Info:", json.dumps(jj.get('client_info', {}), indent=2))
        print("JSON Client Recent History count:", len(jj.get('client_recent_history', [])))
        print("JSON Client Reviews count:", len(jj.get('client_reviews', [])))
        if jj.get('client_reviews'):
            print("First 3 reviews:", json.dumps(jj.get('client_reviews')[:3], indent=2))
    except Exception as e:
        print("JSON parse error:", e)
    
    if raw_html:
        soup = BeautifulSoup(raw_html, 'html.parser')
        # Check headings
        h1s = [h.get_text(strip=True) for h in soup.find_all('h1')]
        print("H1 tags found in raw_html:", h1s)
        titles = [t.get_text(strip=True) for t in soup.find_all('title')]
        print("Title tags in raw_html:", titles)
        # Check client history in html
        history_sections = soup.find_all(attrs={"data-test": True})
        test_attrs = set(h.get('data-test') for h in history_sections)
        print("Data-test attrs related to history/reviews:", [a for a in test_attrs if 'history' in a.lower() or 'review' in a.lower() or 'feedback' in a.lower() or 'client' in a.lower()])
        # Save raw_html to a temporary file for deeper inspection
        with open('inspect_job_sample.html', 'w', encoding='utf-8') as f:
            f.write(raw_html)
        print("Saved raw_html to inspect_job_sample.html")
