import sqlite3
import json
import re
from bs4 import BeautifulSoup
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_daily_2026-10-20.db")
row = conn.execute("SELECT job_json, raw_html FROM jobs WHERE job_id LIKE '%022112660193329382861%'").fetchone()
conn.close()

if not row:
    print("Job not found")
    sys.exit(0)

jj, raw = row
d = json.loads(jj)

print("Title:", d.get("job_title"))
print("Saved client history items:", len(d.get("client_recent_history") or []))
for idx, r in enumerate(d.get("client_recent_history") or []):
    print(f"  [{idx+1}] {r.get('job_title')} (★{r.get('rating')}) | FL: {r.get('freelancer_name')} | Feedback: {r.get('feedback')[:60] if r.get('feedback') else 'None'}")

# Now inspect raw_html for this job
soup = BeautifulSoup(raw, "html.parser")
m = re.search(r"Client's recent history\s*\((\d+)\)", raw)
print(f"\nHeader in raw_html: Client's recent history ({m.group(1) if m else 'N/A'})")

# Check all items in raw_html
items = soup.select(".air3-card-section .items, [data-test='client-history'] section, .extra-jobs-cards .air3-card")
print(f"Elements in raw_html: {len(items)}")

# How many contracts are listed in raw_html?
titles = soup.find_all("a", class_=lambda c: c and "job-link" in str(c))
print(f"Job links found in raw_html: {len(titles)}")
for t in titles[:10]:
    print("  Link title:", t.get_text(strip=True))
