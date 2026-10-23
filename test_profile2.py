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

print(f"Starting Chrome on port {port} with profile 2...")
chrome_proc = subprocess.Popen(args)

try:
    time.sleep(3)
    for _ in range(10):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
                if r.status == 200:
                    print("CDP connected to port 9223!")
                    break
        except Exception:
            time.sleep(1)

    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        context = browser.contexts[0] if browser.contexts else browser.new_context()
        page = context.pages[0] if context.pages else context.new_page()
        page.wait_for_timeout(4000)
        print("Page opened. Current URL:", page.url)
        print("Page Title:", page.title())
        
        # Check if job cards exist
        cards = page.locator("[data-test='job-tile-list'] > section, article.job-tile, div[data-test='JobTile'], section[data-test='JobTile']")
        count = cards.count()
        print(f"Found {count} job cards on page.")

        # Take screenshot for diagnosis
        page.screenshot(path="output/live_test_profile2.png")
        print("Screenshot saved to output/live_test_profile2.png")
        browser.close()
finally:
    try:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=3)
    except Exception:
        pass
    print("Test finished.")
