import sqlite3, sys
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("SELECT raw_html FROM jobs WHERE job_id = '~022105657012753037696'")
raw_html = cur.fetchone()[0]

soup = BeautifulSoup(raw_html, 'html.parser')
sec = soup.select_one("[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history")
if not sec:
    for s in soup.find_all(['section', 'div']):
        h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
        if h and 'recent history' in h.get_text().lower():
            sec = s
            break

items = sec.select('div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], .up-card-sub-section, .history-item, li.air3-card-list-item, article')

for i, item in enumerate(items[:6]):
    fl_el = item.select_one("a[href*='/freelancers/'], [data-test='freelancer-name'], .freelancer-name, .rr-mask")
    fl_name = fl_el.get_text(strip=True) if fl_el else "Unknown Freelancer"
    
    spans = item.select('span[id^="air3-truncation-"]')
    
    before_spans = []
    after_spans = []
    
    item_str = str(item)
    fl_pos = item_str.find(str(fl_el)) if fl_el else -1
    
    for sp in spans:
        sp_text = sp.get_text(strip=True)
        sp_pos = item_str.find(str(sp))
        if fl_pos != -1 and sp_pos > fl_pos:
            after_spans.append(sp_text)
        else:
            before_spans.append(sp_text)
            
    print(f"\nItem #{i+1} | Freelancer: {fl_name}")
    print(f"  BEFORE Freelancer (Freelancer -> Client): {before_spans}")
    print(f"  AFTER Freelancer  (Client -> Freelancer): {after_spans}")
