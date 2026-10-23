import sys
sys.path.insert(0, ".")
from collector.extraction.job_parser import parse_job_detail_page
from bs4 import BeautifulSoup
import re

with open("scratch/scratch_latest_job.html", "r", encoding="utf-8") as f:
    html = f.read()

soup = BeautifulSoup(html, "html.parser")

# Check where description is
print("1. [data-test='job-description-text']:", len(soup.select("[data-test='job-description-text']")))
print("2. [data-test='Description']:", len(soup.select("[data-test='Description']")))
print("3. .job-description:", len(soup.select(".job-description")))
print("4. [class*='description']:", len(soup.select("[class*='description']")))

# Check SSR payload __NUXT_DATA__
nuxt = soup.find("script", id="__NUXT_DATA__")
print("5. __NUXT_DATA__ present:", nuxt is not None)
if nuxt:
    import json
    data = json.loads(nuxt.string)
    # Search for long text strings in Nuxt payload
    long_strings = [s for s in data if isinstance(s, str) and len(s) > 100]
    print(f"Found {len(long_strings)} strings > 100 chars in Nuxt payload.")
    for i, s in enumerate(long_strings[:3]):
        print(f"  String {i} ({len(s)} chars): {s[:100]}...")
