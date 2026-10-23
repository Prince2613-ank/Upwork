import subprocess
import time
import os
from playwright.sync_api import sync_playwright

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
p_dir = os.path.join(USERPROFILE, "chrome_upwork_profile")
port = 9222

url = "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"

args = [
    CHROME_EXE,
    f"--remote-debugging-port={port}",
    f"--user-data-dir={p_dir}",
    "--disable-fre",
    "--no-default-browser-check",
    "--no-first-run",
    url
]

p = subprocess.Popen(args)
time.sleep(3)

try:
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=10000)
        ctx = browser.contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.wait_for_timeout(3000)
        print(f"Port 9222 Page Title: {page.title()}")
        print(f"Port 9222 Page URL: {page.url}")
        browser.close()
finally:
    p.terminate()
    p.wait()
