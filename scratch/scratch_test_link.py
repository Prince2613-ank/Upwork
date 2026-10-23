from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    link = page.locator('a[data-test="job-tile-title-link"]').first
    print("Link text:", link.inner_text())
    print("Link uid:", link.get_attribute("data-ev-job-uid"))
    print("Link href:", link.get_attribute("href"))
