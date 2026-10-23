import subprocess
import time
import os
from playwright.sync_api import sync_playwright
from collector.extraction.search_parser import parse_search_page_html
from collector.extraction.job_parser import parse_job_detail_page

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = os.path.join(USERPROFILE, "chrome_upwork_profile_2")
port = 9223

args = [
    CHROME_EXE,
    f"--remote-debugging-port={port}",
    f"--user-data-dir={profile}",
    "--disable-fre",
    "--no-default-browser-check",
    "--no-first-run",
    "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"
]

chrome_proc = subprocess.Popen(args)

try:
    time.sleep(3)
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0]
        page = context.pages[0]
        
        # Wait up to 15s for Cloudflare to clear
        for i in range(15):
            t = page.title()
            if "just a moment" not in t.lower() and "loading" not in t.lower():
                break
            time.sleep(1)
            
        time.sleep(2)
        html = page.content()
        cards = parse_search_page_html(html)
        print(f"Extracted {len(cards)} search cards.")
        
        # Test first card detail
        card = cards[0]
        job_url = card.get("job_url")
        search_title = card.get("job_title")
        print(f"Navigating to detail: {search_title} ({job_url})...")
        
        detail_page = context.new_page()
        detail_page.goto(job_url, timeout=30000, wait_until="domcontentloaded")
        detail_page.wait_for_timeout(3000)
        
        # Wait if Cloudflare shows up on detail page
        for i in range(10):
            dt = detail_page.title()
            if "just a moment" not in dt.lower():
                break
            time.sleep(1)
            
        detail_html = detail_page.content()
        job_obj = parse_job_detail_page(detail_html, job_url=job_url, search_card_metadata=card)
        
        print("\n=== EXTRACTED JOB DETAIL ===")
        print("Search Title:", search_title)
        print("Parsed Title:", job_obj.job_title)
        print("Titles Match:", search_title.strip() == job_obj.job_title.strip())
        print("Description Length:", len(job_obj.job.description))
        print("Client Location:", job_obj.client_location)
        print("Client Total Spent:", job_obj.client.total_spent)
        print("Client Rating:", job_obj.client.rating)
        print("Client Payment Verified:", job_obj.client.payment_verified)
        print("Client Recent History Count:", len(job_obj.client_recent_history))
        for h in job_obj.client_recent_history[:3]:
            print("  Review Title:", h.job_title)
            print("  Review Feedback:", (h.feedback or "")[:60])
            print("  Freelancer:", h.freelancer_name)
        
        detail_page.close()
        browser.close()
finally:
    try:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=3)
    except Exception:
        pass
