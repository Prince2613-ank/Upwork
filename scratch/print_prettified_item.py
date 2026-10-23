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

print("PRETTIFIED HTML OF ITEM #2:")
print(items[1].prettify()[3000:7000])
