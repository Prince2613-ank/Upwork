from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://[::1]:9223")
    page = browser.contexts[0].pages[0]
    print("Navigating to Upwork search...")
    url = "https://www.upwork.com/nx/search/jobs?location=Japan&per_page=50&sort=recency"
    page.goto(url, wait_until="domcontentloaded")
    print("Current URL:", page.url)
    print("Waiting 5s for cards...")
    time.sleep(5)
    page.screenshot(path="scratch/chrome_japan_search.png")
    
    # Check selectors
    selectors = [
        '[data-test="JobTile"]',
        'article[data-test="JobTile"]',
        'section.air3-card-section',
        '.job-tile',
        '[data-test="job-tile-list"]',
        '.up-card-section',
        '[data-test="search-result-empty"]',
        '[data-test="empty-state"]'
    ]
    for sel in selectors:
        cnt = page.locator(sel).count()
        print(f"Selector {sel}: {cnt}")
        
    print("Title:", page.title())
    text = page.evaluate("document.body ? document.body.innerText.slice(0, 500) : ''")
    print("Page text sample:", repr(text))
