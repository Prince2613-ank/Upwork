import sys
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(r"c:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence")
sys.path.insert(0, str(ROOT))

from run_daily_system import extract_search_cards

COMBINED_LOCATIONS_PARAM = (
    "Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,"
    "Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,"
    "United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,"
    "United%2520States%2520Virgin%2520Islands"
)
COMBINED_SEARCH_URL = (
    f"https://www.upwork.com/nx/search/jobs?"
    f"location={COMBINED_LOCATIONS_PARAM}&"
    f"payment_verified=1&per_page=50&sort=recency"
)

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()

    url = f"{COMBINED_SEARCH_URL}&page=1"
    print(f"Loading {url[:80]}...")
    page.goto(url, timeout=25000, wait_until="domcontentloaded")
    time.sleep(2.0)
    print(f"Title: {page.title()}")
    cards = extract_search_cards(page)
    print(f"Extracted {len(cards)} cards on Page 1.")
    if cards:
        print("First card:", cards[0].get("job_title"), "|", cards[0].get("posted_raw"), "|", cards[0].get("client_location"))
        print("Last card:", cards[-1].get("job_title"), "|", cards[-1].get("posted_raw"), "|", cards[-1].get("client_location"))
