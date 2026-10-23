import subprocess
import time
import os
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from collector.extraction.search_parser import parse_search_page_html, parse_search_card

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
            print(f"[{i}] {t}")
            if "just a moment" not in t.lower() and "loading" not in t.lower():
                break
            time.sleep(1)
            
        time.sleep(3)
        html = page.content()
        soup = BeautifulSoup(html, "html.parser")
        
        articles = soup.find_all("article")
        sections = soup.find_all("section")
        links = soup.find_all("a", href=True)
        job_links = [a['href'] for a in links if '/jobs/' in a['href']]
        
        print(f"Articles: {len(articles)}, Sections: {len(sections)}, Job Links: {len(job_links)}")
        if job_links:
            print("First 3 job links:", job_links[:3])
            
        cards = parse_search_page_html(html)
        print(f"Cards parsed by search_parser: {len(cards)}")
        browser.close()
finally:
    try:
        chrome_proc.terminate()
        chrome_proc.wait(timeout=3)
    except Exception:
        pass
