from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    print("URL:", page.url)
    print("Title:", page.title())
    text = page.evaluate("() => document.body ? document.body.innerText : ''")
    print("Body length:", len(text))
    print("Body snippet:\n", text[:500])
