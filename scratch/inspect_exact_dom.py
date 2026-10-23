import sqlite3, sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT raw_html FROM jobs WHERE job_id = '~022105657012753037696'")
row = cur.fetchone()

if row and row[0]:
    raw_html = row[0]
    soup = BeautifulSoup(raw_html, 'html.parser')
    sec = soup.select_one("[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history")
    if not sec:
        for s in soup.find_all(['section', 'div']):
            h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
            if h and 'recent history' in h.get_text().lower():
                sec = s
                break
    if sec:
        items = sec.select('div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], .up-card-sub-section, .history-item, li.air3-card-list-item, article')
        print(f"Found {len(items)} history items in section!")
        for i, item in enumerate(items[:3]):
            print(f"\n=================== ITEM #{i+1} ===================")
            # print all text with labels
            for descendant in item.descendants:
                if descendant.name and descendant.name in ['p', 'span', 'div', 'strong', 'h4', 'h5', 'a']:
                    classes = descendant.get('class', [])
                    did = descendant.get('id', '')
                    dtest = descendant.get('data-test', '')
                    text = descendant.get_text(strip=True)
                    if text and len(text) > 3 and not any(child.name in ['p', 'span', 'div'] for child in descendant.children if hasattr(child, 'name')):
                        print(f"[{descendant.name} id='{did}' data-test='{dtest}' class='{' '.join(classes[:3])}']: {text}")
