import sqlite3
import json
import sys
from collector.extraction.job_parser import parse_job_detail_page
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_today.db")
row = conn.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE job_id LIKE '%022111270348951686753%'").fetchone()
conn.close()

if not row:
    print("Row not found!")
    sys.exit()

jid, jjson, raw_html = row
print(f"Loaded job {jid}, HTML len: {len(raw_html)}")

# Test parse_job_detail_page
job_obj = parse_job_detail_page(raw_html, job_url=f"https://www.upwork.com/jobs/{jid}/")
d = job_obj.model_dump(mode="json")

print("\n--- Current parse_job_detail_page output ---")
print("Title:", d.get("job_title"))
print("Description len:", len((d.get("job") or {}).get("description") or d.get("description") or ""))
print("Description preview:", repr(((d.get("job") or {}).get("description") or "")[:200]))
print("Client:", d.get("client"))
print("Client Recent History:", len(d.get("client_recent_history") or []))

# Inspect HTML directly
soup = BeautifulSoup(raw_html, "html.parser")
print("\n--- Inspecting raw_html directly ---")
# 1. Nuxt data
if "__NUXT_DATA__" in raw_html:
    print("Contains __NUXT_DATA__ script!")
else:
    print("NO __NUXT_DATA__ found!")

# 2. Descriptions in DOM
desc_el = soup.select_one('[data-test="job-description-text"], [data-test="JobDescription"], .job-description, [itemprop="description"]')
print("Selector [data-test='job-description-text']:", desc_el is not None)
if desc_el:
    print("desc_el text:", repr(desc_el.get_text()[:200]))

# Search for "Nomad Equity" in raw_html
if "Nomad Equity" in raw_html:
    print("--> Found 'Nomad Equity' in raw_html!")
    idx = raw_html.find("Nomad Equity")
    print("Context around Nomad Equity:", repr(raw_html[max(0, idx-100):idx+300]))
else:
    print("--> 'Nomad Equity' NOT found in raw_html!")

# Search for "Yorba Linda" in raw_html
if "Yorba Linda" in raw_html:
    print("--> Found 'Yorba Linda' in raw_html!")
else:
    print("--> 'Yorba Linda' NOT in raw_html!")

# Search for "Client's recent history" in raw_html
if "recent history" in raw_html.lower():
    print("--> Found 'recent history' in raw_html!")
else:
    print("--> 'recent history' NOT in raw_html!")
