import sys
import os
import subprocess
import time
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.abspath("."))
from collector.extraction.review_parser import parse_client_history
from bs4 import BeautifulSoup

port = 9224
profile = r"C:\Users\princ\chrome_upwork_profile_3"
chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
job_url = "https://www.upwork.com/jobs/Affiliate-Marketing-Pro-Scale-Campaign_~022104107742589813869/"

def wait_for_cloudflare_clear(page, timeout_sec=30):
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            title = page.title().lower()
            if "just a moment" not in title and "attention required" not in title and "security verification" not in title:
                return True
            for frame in page.frames:
                try:
                    cb = frame.locator("input[type='checkbox'], .ctp-checkbox-label, div#cf-stage")
                    if cb.count() > 0:
                        cb.first.click()
                        time.sleep(2)
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(1)
    return False

print(f"Starting Chrome on port {port}...")
args = [
    chrome_exe,
    f"--remote-debugging-port={port}",
    f"--user-data-dir={profile}",
    "--disable-fre",
    "--no-default-browser-check",
    "--no-first-run",
    "about:blank"
]
proc = subprocess.Popen(args)
time.sleep(3)

try:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=15000)
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.new_page()
        
        print(f"Navigating to {job_url}...")
        try:
            page.goto(job_url, timeout=45000, wait_until="domcontentloaded")
        except Exception as e:
            print("Initial goto note:", e)
            
        print("Waiting for Cloudflare clear...")
        cleared = wait_for_cloudflare_clear(page, timeout_sec=25)
        print("Cloudflare cleared:", cleared)
        time.sleep(5)
        
        # Ensure page finished loading
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:
            pass
        
        print("Page URL:", page.url)
        print("Page Title:", page.title())
        
        # Scroll down
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)
        
        content = page.content()
        print("Contains 'Client\\'s recent history':", "Client's recent history" in content or "client's recent history" in content.lower())
        print("Contains 'Jobs in progress':", "Jobs in progress" in content)
        
        items = parse_client_history(content)
        print(f"Parsed {len(items)} history items!")
        for it in items[:3]:
            print("  Title:", it.job_title, "| Amount:", it.amount, "| Rating:", it.rating, "| FB:", it.feedback[:60])
        page.screenshot(path="scratch/job_screenshot.png")
        print("Screenshot saved to scratch/job_screenshot.png")
        browser.close()
finally:
    try:
        proc.terminate()
        proc.wait(timeout=3)
    except Exception:
        pass
