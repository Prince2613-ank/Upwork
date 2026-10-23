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

print(f"Total items found: {len(items)}\n")

for idx, it in enumerate(items):
    # Job Title
    title_el = it.select_one("[data-cy='job-title'], h4, strong")
    title = title_el.get_text(strip=True) if title_el else "Unknown Job"
    
    # Split by "To freelancer:"
    # In BeautifulSoup, find the element or text node "To freelancer:"
    to_fl_node = None
    for text_node in it.find_all(string=True):
        if "to freelancer:" in text_node.lower():
            to_fl_node = text_node
            break
            
    # Find all truncation spans in it
    spans = it.select('span[id^="air3-truncation-"]')
    
    fl_to_client_text = ""
    client_to_fl_text = ""
    
    if to_fl_node:
        # Check parent of to_fl_node
        to_fl_container = to_fl_node.parent
        # Any span before to_fl_container is FL -> Client
        # Any span inside or after to_fl_container is Client -> FL
        item_html = str(it)
        split_pos = item_html.lower().find("to freelancer:")
        for sp in spans:
            sp_text = sp.get_text(" ", strip=True)
            sp_pos = item_html.find(str(sp))
            if sp_pos < split_pos:
                fl_to_client_text = sp_text
            else:
                client_to_fl_text = sp_text
    else:
        if spans:
            fl_to_client_text = spans[0].get_text(" ", strip=True)
            
    print(f"[{idx+1}] {title[:40]}")
    print(f"    ⭐ Freelancer TO Client: '{fl_to_client_text}'")
    print(f"    💬 Client TO Freelancer: '{client_to_fl_text}'")
    print()
