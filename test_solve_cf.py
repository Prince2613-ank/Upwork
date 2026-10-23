import subprocess
import time
import os
import urllib.request
from playwright.sync_api import sync_playwright

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
        
        for i in range(10):
            t = page.title()
            print(f"[{i}] Title: {t}")
            if "just a moment" not in t.lower():
                print("Cloudflare passed!")
                break
            
            # Look for iframe or turnstile checkbox
            for frame in page.frames:
                try:
                    cb = frame.locator("input[type='checkbox'], .ctp-checkbox-label, div#cf-stage")
                    if cb.count() > 0:
                        print("Clicking Turnstile checkbox in frame...")
                        cb.first.click()
                        time.sleep(2)
                except Exception:
                    pass
            time.sleep(2)
            
        print("Final title:", page.title())
        cards = page.locator("[data-test='job-tile-list'] > section, article.job-tile, div[data-test='JobTile'], section[data-test='JobTile']")
        print(f"Cards found: {cards.count()}")
        page.screenshot(path="output/turnstile_result.png")
        browser.close()
finally:
    try:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=3)
    except Exception:
        pass
