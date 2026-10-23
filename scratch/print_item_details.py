import sqlite3
from bs4 import BeautifulSoup

conn = sqlite3.connect('output/database_today.db')
html = conn.execute("SELECT raw_html FROM jobs WHERE job_id='~022111886000493967691'").fetchone()[0]
soup = BeautifulSoup(html, 'html.parser')
item = soup.select_one('div.item[data-cy="job"]')
print(item.prettify())
