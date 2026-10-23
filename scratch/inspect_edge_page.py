from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    for p in ctx.pages:
        if "upwork.com" in p.url:
            print("Upwork Page URL:", p.url)
            print("Upwork Page Title:", p.title())
            # check if cloudflare
            cf = p.locator("text='Just a moment'").count()
            print("Cloudflare count:", cf)
            # check if modal/drawer
            drawer = p.locator("[class*='slider'], [class*='drawer'], [role='dialog'], [aria-modal='true']").count()
            print("Modal/Drawer count:", drawer)
            # check if error
            err = p.locator("text='Something went wrong'").count()
            print("Error text count:", err)
            # Check current visible text
            body_text = p.evaluate("() => document.body ? document.body.innerText.substring(0, 300) : ''")
            print("Body snippet:\n", body_text)
