import sqlite3, sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT raw_html FROM jobs WHERE raw_html IS NOT NULL LIMIT 30")
rows = cur.fetchall()

count_1span = 0
for r in rows:
    raw_html = r[0]
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
        for item in items:
            spans = item.select('span[id^="air3-truncation-"]')
            if len(spans) == 1:
                # Let's see where this span is relative to freelancer name
                fl_el = item.select_one("a[href*='/freelancers/'], [data-test='freelancer-name'], .freelancer-name, .rr-mask")
                fl_name = fl_el.get_text(strip=True) if fl_el else "Unknown"
                item_str = str(item)
                fl_pos = item_str.find(str(fl_el)) if fl_el else -1
                sp_pos = item_str.find(str(spans[0]))
                position = "BEFORE (FL->Client)" if sp_pos < fl_pos else "AFTER (Client->FL)"
                print(f"Position: {position} | Freelancer: {fl_name}")
                print(f"  Text: {spans[0].get_text(strip=True)[:120]}")
                count_1span += 1
                if count_1span >= 10:
                    break
        if count_1span >= 10:
            break
