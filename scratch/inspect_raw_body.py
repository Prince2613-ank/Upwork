import sqlite3
import bs4
import sys

sys.stdout.reconfigure(encoding='utf-8')
conn = sqlite3.connect('output/database_today.db')
row = conn.execute("SELECT raw_html FROM jobs WHERE job_id LIKE '%022111270348951686753%'").fetchone()
conn.close()

raw_html = row[0]
print(f"Total HTML len: {len(raw_html)}")
print("\n--- FIRST 800 CHARS ---")
print(raw_html[:800])
print("\n--- LAST 800 CHARS ---")
print(raw_html[-800:])
print("\nTags in HTML:")
soup = bs4.BeautifulSoup(raw_html, 'html.parser')
for t in soup.find_all(True):
    print(t.name, list(t.attrs.keys()))
