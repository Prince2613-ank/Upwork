import sqlite3
from bs4 import BeautifulSoup

conn = sqlite3.connect('output/database_today.db')
rows = conn.execute("SELECT job_id, raw_html FROM jobs WHERE raw_html IS NOT NULL").fetchall()

count = 0
for jid, html in rows:
    if 'client-history' in html or 'contract-history' in html:
        soup = BeautifulSoup(html, 'html.parser')
        sec = soup.select_one('[data-test="client-history"], [data-test="contract-history"], .client-history, #client-history')
        if sec:
            items = sec.select('div.item[data-cy="job"]')
            for it in items:
                spans = it.select('span[id^="air3-truncation-"]')
                if len(spans) >= 2:
                    s1 = spans[0]
                    s2 = spans[1]
                    
                    # Check parent hierarchy for 'To freelancer'
                    p1_text = s1.find_parent(lambda tag: tag.name == 'div' and 'To freelancer' in tag.get_text())
                    p2_text = s2.find_parent(lambda tag: tag.name == 'div' and 'To freelancer' in tag.get_text())
                    
                    link = it.select_one('a')
                    title = link.get_text(strip=True) if link else "Unknown"
                    print(f"Contract: {title}")
                    print(f"  Span 1 (is inside 'To freelancer'? {p1_text is not None}): {s1.get_text(strip=True)[:100]}")
                    print(f"  Span 2 (is inside 'To freelancer'? {p2_text is not None}): {s2.get_text(strip=True)[:100]}")
                    count += 1
                    break
        if count >= 5:
            break
