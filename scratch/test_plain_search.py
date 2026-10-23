from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://[::1]:9223")
    page = browser.contexts[0].pages[0]
    
    print("Navigating to plain jobs search...")
    page.goto("https://www.upwork.com/nx/search/jobs/?sort=recency", wait_until="domcontentloaded")
    print("URL:", page.url)
    time.sleep(6)
    page.screenshot(path="scratch/chrome_plain_search.png")
    
    tiles = page.locator('[data-test="JobTile"]').count()
    sections = page.locator('section.air3-card-section').count()
    articles = page.locator('article').count()
    print(f"JobTile count: {tiles}, sections: {sections}, articles: {articles}")
    
    text = page.evaluate("document.body ? document.body.innerText.slice(0, 400) : ''")
    print("Text:", repr(text))
