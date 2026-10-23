import sys
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    try:
        browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=5000)
        pages = browser.contexts[0].pages
        print("Chrome Pages count:", len(pages))
        for i, pg in enumerate(pages):
            print(f"Page {i}: url={pg.url} title={pg.title()}")
            pg.screenshot(path=f"scratch/chrome_live_{i}.png")
    except Exception as e:
        print("Chrome inspect error:", e)
