from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import re

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    job_pages = [pg for pg in b.contexts[0].pages if "upwork.com/jobs/" in pg.url]
    if not job_pages:
        print("No job page open in Chrome")
        exit(0)
    page = job_pages[0]
    print("Inspecting job:", page.url)
    html = page.content()
    soup = BeautifulSoup(html, "html.parser")

    print("\n--- 1. JSON-LD Schema ---")
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string)
            print("datePosted in JSON-LD:", data.get("datePosted"))
            print("title:", data.get("title"))
        except Exception:
            pass

    print("\n--- 2. Nuxt SSR Payload Dates ---")
    nuxt = soup.find("script", id="__NUXT_DATA__")
    if nuxt and nuxt.string:
        # Search for ISO date patterns in Nuxt payload
        dates = re.findall(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[^\"]*", nuxt.string)
        print("Found Nuxt ISO dates:", dates[:10])

    print("\n--- 3. Time tags or datetime attributes ---")
    for t in soup.find_all(attrs={"datetime": True}):
        print("datetime attribute:", t.name, t.attrs, t.get_text()[:40])

    print("\n--- 4. Search for 'posted' or 'created' or 'publish' keywords in Nuxt ---")
    if nuxt and nuxt.string:
        matches = re.findall(r'"([^"]*(?:publish|posted|created|date)[^"]*)":\s*"?([^",}]+)"?', nuxt.string, re.I)
        print("Nuxt key-value matches:", matches[:10])
