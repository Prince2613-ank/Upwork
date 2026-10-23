import sqlite3
from bs4 import BeautifulSoup

conn = sqlite3.connect('output/database_today.db')
html = conn.execute("SELECT raw_html FROM jobs WHERE job_id='~022111886000493967691'").fetchone()[0]
soup = BeautifulSoup(html, 'html.parser')
sec = soup.select_one('[data-test="client-history"], [data-test="contract-history"], .client-history, #client-history')
if not sec:
    for s in soup.find_all(['section', 'div', 'article']):
        h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
        if h and ("recent history" in h.get_text().lower() or "client history" in h.get_text().lower()):
            sec = s
            break

items = sec.select('div.item[data-cy="job"]')
print("Found items:", len(items))
for idx, it in enumerate(items):
    title = it.select_one('a.js-job-link')
    t_text = title.get_text(strip=True) if title else "No Title"
    
    # Freelancer to client review
    # Notice: the top rating & feedback is before 'To freelancer:'
    # Let's inspect the divs inside it.select('.main > div')
    main_div = it.select_one('.main')
    print(f"\n--- Item {idx+1}: {t_text} ---")
    for child in main_div.children:
        if child.name:
            text = child.get_text(" ", strip=True)
            if "to freelancer" in text.lower():
                print(f"  [CLIENT -> FREELANCER (DISCARD)]: {text}")
            else:
                print(f"  [FREELANCER -> CLIENT (KEEP)]: {text}")
