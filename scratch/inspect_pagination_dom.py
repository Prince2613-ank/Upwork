import sqlite3
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_daily_2026-10-20.db")
row = conn.execute("SELECT raw_html FROM jobs WHERE job_id LIKE '%022112658363064905128%'").fetchone()
conn.close()

html = row[0]
soup = BeautifulSoup(html, "html.parser")

tag = soup.find(lambda t: t.string and "Client's recent history" in t.string)
container = tag.find_parent("div", class_="air3-card")

# Check all siblings of section 1 or footer of container
print("Container direct children:", [c.name for c in container.children if hasattr(c, 'name')])
sec1 = container.find_all("section")[1]
print("Sec1 parent:", sec1.parent.name, sec1.parent.get('class'))
print("Next sibling of Sec1:", sec1.next_sibling)

# Let's check parent 4 (extra-jobs-cards) children:
parent4 = container.find_parent("div", class_="extra-jobs-cards")
if parent4:
    print("\nParent 4 (extra-jobs-cards) children:")
    for c in parent4.children:
        if hasattr(c, 'name'):
            print(f"  <{c.name}> class={c.get('class')} id={c.get('id')} text_sample={c.get_text(' ')[:100]}")
