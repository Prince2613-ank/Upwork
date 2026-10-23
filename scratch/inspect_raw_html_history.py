import sqlite3
import json
import re
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_daily_2026-10-20.db")
row = conn.execute("SELECT raw_html FROM jobs WHERE job_id LIKE '%022112658363064905128%'").fetchone()
conn.close()

if not row:
    print("Job not found in database_daily_2026-10-20.db")
    sys.exit(0)

html = row[0]
soup = BeautifulSoup(html, "html.parser")

# Check history items
hist_items = soup.select('[data-test="client-history"] section, .client-history section, [data-test="history-item"], .extra-jobs-cards section, [data-qa="client-recent-history"] > div')
print(f"Total HTML history elements found: {len(hist_items)}")

# Check text occurrences
print("Has 'Part-Time Finance Specialist':", "Part-Time Finance Specialist" in html)
print("Has 'Marketing Manager for A Backflow Company':", "Marketing Manager for A Backflow Company" in html)
print("Has 'Data collection/entry':", "Data collection/entry" in html)
print("Has 'Client\'s recent history':", "Client's recent history" in html)

# Search for total count
m_total = re.search(r"Client's recent history\s*\((\d+)\)", html, re.I)
if m_total:
    print(f"Header indicates total history count: {m_total.group(1)}")

# Check for pagination / buttons
pagination = soup.select('[data-test="client-history"] nav, [data-test="client-history"] ul.pagination, .air3-pagination, ul.air3-pagination')
print(f"Pagination elements found: {len(pagination)}")
for p in pagination:
    print("Pagination HTML:", str(p)[:200])

# Check for all buttons in client history section
sec = soup.select_one('[data-test="client-history"], [data-qa="client-recent-history"], .client-history')
if sec:
    btns = sec.find_all(["button", "a"])
    print(f"Buttons/links in client history section: {len(btns)}")
    for b in btns:
        print(f"  Tag: <{b.name}> Text: '{b.get_text(strip=True)}' Class: {b.get('class')} attrs: {b.attrs}")
else:
    print("Could not find client history section container directly")

# Check if there are Nuxt data / JSON embedded
nuxt_matches = re.findall(r'<script[^>]*__NUXT_DATA__[^>]*>(.*?)</script>', html, re.DOTALL)
print(f"Nuxt data scripts: {len(nuxt_matches)}")
if nuxt_matches:
    print("Nuxt data snippet length:", len(nuxt_matches[0]))
    # Search for titles in Nuxt data
    print("Nuxt contains 'Jordan C':", "Jordan C" in nuxt_matches[0])
    print("Nuxt contains 'Delano':", "Delano" in nuxt_matches[0])
    print("Nuxt contains 'Part-Time Finance':", "Part-Time Finance" in nuxt_matches[0])
