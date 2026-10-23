import sqlite3
from bs4 import BeautifulSoup

conn = sqlite3.connect('output/database_today.db')
rows = conn.execute("SELECT job_id, raw_html FROM jobs WHERE raw_html IS NOT NULL").fetchall()

for jid, html in rows:
    if 'client-history' in html or 'contract-history' in html or 'recent history' in html.lower():
        soup = BeautifulSoup(html, 'html.parser')
        sec = soup.select_one('[data-test="client-history"], [data-test="contract-history"], .client-history, #client-history')
        if not sec:
            for s in soup.find_all(['section', 'div', 'article']):
                h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
                if h and ("recent history" in h.get_text().lower() or "client history" in h.get_text().lower()):
                    sec = s
                    break
        if sec:
            items = sec.select('div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], .up-card-sub-section, .history-item, li.air3-card-list-item, article, [data-ev-label="contract_history_item"]')
            if len(items) >= 3:
                print(f"Job ID: {jid}")
                print(f"Total history items found in HTML: {len(items)}")
                
                # Check for pagination / view more
                for b in sec.find_all(['button', 'a', 'nav']):
                    txt = b.get_text(strip=True)
                    if txt:
                        print(f"  Element <{b.name}>: '{txt}' | class={b.get('class')} | data-test={b.get('data-test')}")
                
                # Check first item details
                first_item = items[0]
                print("\n--- FIRST ITEM HTML SNIPPET ---")
                print(first_item.prettify()[:1500])
                break
