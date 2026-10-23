from playwright.sync_api import sync_playwright
import sys
from collector.extraction.job_parser import parse_job_detail_page
import json

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    for page in ctx.pages:
        print(f"Tab: {page.title()[:40]} | URL: {page.url[:60]}")
        if "022111270348951686753" in (page.url or ""):
            print("FOUND TAB IN CHROME!")
            c = page.content()
            print("Content length:", len(c))
            job_obj = parse_job_detail_page(c, job_url=page.url)
            d = job_obj.model_dump(mode="json")
            print("Title:", d.get("job_title"))
            print("Desc len:", len((d.get("job") or {}).get("description") or d.get("description") or ""))
            print("Desc sample:", repr(((d.get("job") or {}).get("description") or "")[:200]))
            print("Client:", d.get("client"))
            print("Recent history count:", len(d.get("client_recent_history") or []))
            for h in (d.get("client_recent_history") or [])[:3]:
                print("   Review:", h.get("freelancer_name"), "|", h.get("rating"), "|", repr(h.get("feedback", "")[:80]))
