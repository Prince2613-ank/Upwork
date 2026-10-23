import subprocess
import time
from playwright.sync_api import sync_playwright

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = r"C:\Users\princ\chrome_upwork_profile_2"
cmd = [CHROME_EXE, "--remote-debugging-port=9223", f"--user-data-dir={profile}", "about:blank"]
proc = subprocess.Popen(cmd)
time.sleep(2)

try:
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
        page = browser.contexts[0].new_page()
        page.goto("https://www.upwork.com/jobs/Affiliate-Marketing-Pro-to-Scale-Campaign_~022104107742589813869/", timeout=30000, wait_until="domcontentloaded")
        time.sleep(2)
        print("Title:", page.title())
        print("URL:", page.url)
        html = page.content()
        print("HTML length:", len(html))
        for term in ["recent history", "work-history", "client-history", "38k total spent", "new york city"]:
            print(f"Contains '{term}':", term in html.lower())

        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(3)
        html2 = page.content()
        print("After Scroll - Contains 'recent history':", "recent history" in html2.lower())
        page.close()
        browser.close()
finally:
    proc.terminate()
