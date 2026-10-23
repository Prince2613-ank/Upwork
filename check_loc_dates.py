from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9223')
    page = browser.contexts[0].pages[0]
    
    for loc, p_num in [("Canada", 10), ("Australia and New Zealand", 10), ("United Kingdom", 45)]:
        url = f"https://www.upwork.com/nx/search/jobs?location={loc}&payment_verified=1&per_page=50&sort=recency&page={p_num}"
        print(f"Checking {loc} Page {p_num}...")
        page.goto(url)
        time.sleep(3)
        tiles = page.query_selector_all("article")
        if tiles:
            text = tiles[0].inner_text().replace("\n", " ")
            print(f"[{loc} p{p_num}]: {len(tiles)} jobs. Top job: {text[:150]}")
        else:
            print(f"[{loc} p{p_num}]: No tiles found (URL: {page.url[:80]})")
