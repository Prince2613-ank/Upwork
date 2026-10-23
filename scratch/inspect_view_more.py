import sqlite3
from bs4 import BeautifulSoup

conn = sqlite3.connect('output/database_today.db')
html = conn.execute("SELECT raw_html FROM jobs WHERE job_id='~022111886000493967691'").fetchone()[0]
soup = BeautifulSoup(html, 'html.parser')
vm = [a for a in soup.find_all(['a', 'button']) if 'view more' in a.get_text().lower()]
for a in vm:
    print(f"Tag: {a.name}, Text: '{a.get_text(strip=True)}', href: {a.get('href')}, attrs: {a.attrs}")
    print("Parent HTML:")
    print(a.parent.prettify()[:500])
