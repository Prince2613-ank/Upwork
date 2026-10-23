from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    print("Chrome 9222 Current URL:", page.url)
    print("Chrome 9222 Current Title:", page.title())
    res = page.evaluate("""() => {
        return {
            articles: document.querySelectorAll('article').length,
            job_tiles: document.querySelectorAll('[data-test="job-tile"]').length,
            job_links: document.querySelectorAll('a[href*="/jobs/"]').length,
            sections: document.querySelectorAll('section').length,
            body_snippet: (document.body?.innerText || '').substring(0, 300)
        };
    }""")
    print("DOM Scan:", res)
