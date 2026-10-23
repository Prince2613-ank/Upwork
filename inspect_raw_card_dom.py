import sqlite3
import json
from bs4 import BeautifulSoup

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()

# Find a job with 'Rating is 5.0 out of 5.' in client_recent_history and has raw_html
row = c.execute("""
    SELECT job_id, job_json, raw_html 
    FROM jobs 
    WHERE raw_html IS NOT NULL AND length(raw_html) > 1000
    LIMIT 20
""").fetchall()
conn.close()

for jid, jj, raw_html in row:
    d = json.loads(jj)
    hist = d.get("client_recent_history") or []
    has_rating_title = any(h.get("job_title", "").startswith("Rating is") for h in hist)
    if has_rating_title:
        print(f"Found Job {jid} with 'Rating is' title!")
        soup = BeautifulSoup(raw_html, "html.parser")
        sec = soup.select_one("[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history")
        if not sec:
            for s in soup.find_all(['section', 'div', 'article']):
                h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
                if h and ("recent history" in h.get_text().lower() or "client history" in h.get_text().lower()):
                    sec = s
                    break
        if sec:
            items = sec.select('div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], .history-item, li.air3-card-list-item, article')
            print(f"Found {len(items)} contract cards in HTML:")
            for idx, it in enumerate(items[:3]):
                print(f"\n--- Card {idx+1} ---")
                print("Text snippet:", repr(it.get_text(separator=' | ')[:250]))
                links = it.find_all("a")
                print("Links:", [(a.get('href'), a.get_text(strip=True)) for a in links])
                headings = it.find_all(["h4", "h5", "strong"])
                print("Headings:", [(h.name, h.get_text(strip=True)) for h in headings])
        break
