"""
Quick diagnosis: save the current search page HTML and check parser.
Run this while Chrome is open on port 9222 and logged into Upwork.
"""
import sys, os, time, json
sys.path.insert(0, os.path.abspath("."))
from playwright.sync_api import sync_playwright
from collector.extraction.search_parser import parse_search_page_html

PORT = 9222
SEARCH_URL = (
    "https://www.upwork.com/nx/search/jobs?"
    "location=Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,"
    "Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,"
    "United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,"
    "United%2520States%2520Virgin%2520Islands&payment_verified=1&per_page=50&sort=recency&page=1"
)

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=15000)
    ctx = browser.contexts[0]
    page = ctx.new_page()

    print(f"Navigating to search page...")
    page.goto(SEARCH_URL, timeout=45000, wait_until="domcontentloaded")
    time.sleep(4)

    html = page.content()
    print(f"HTML size: {len(html):,} bytes")

    # Save for analysis
    with open("output/search_page_diag.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Saved to output/search_page_diag.html")

    # Try parsing
    cards = parse_search_page_html(html)
    print(f"Cards found by parser: {len(cards)}")
    if cards:
        print(f"First card: {cards[0]}")

    # Check what's actually in the HTML
    checks = [
        "job-tile", "job-card", "data-job-uid", "JobTile", "tile-job",
        "upwork-job", "fe-job-tile", "job-list-item",
        "air3-card", "section-title", "search-results",
        "JobSearch", "jobsearch", "job_title", "job-title"
    ]
    print("\nSelector presence check:")
    for c in checks:
        present = c.lower() in html.lower()
        print(f"  '{c}': {'✓ FOUND' if present else '✗ not found'}")

    # Extract a snippet to see actual structure
    idx = html.lower().find("job")
    if idx > 0:
        print(f"\nHTML snippet around first 'job':")
        print(html[max(0,idx-100):idx+500])

    page.close()
    browser.close()
