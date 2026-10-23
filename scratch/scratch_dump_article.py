from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    html = page.evaluate("() => document.querySelector('article') ? document.querySelector('article').outerHTML : 'NO ARTICLE'")
    with open("scratch/scratch_art1.html", "w", encoding="utf-8") as f:
        f.write(html)
    print("Article outerHTML saved. Length:", len(html))
