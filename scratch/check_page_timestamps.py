from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')
    ctx = browser.contexts[0]
    page = ctx.pages[0]
    print('Current Page URL:', page.url)
    
    cards = page.evaluate("""() => {
        const sections = Array.from(document.querySelectorAll('article, [data-test="job-tile-list"] > section'));
        return sections.slice(0, 8).map(s => {
            const t = s.querySelector('[data-test="posted-on"], [class*="posted"], small, span');
            const h = s.querySelector('h3, h2, [data-test="job-title"]');
            return {
                title: h ? h.innerText.trim() : 'No Title',
                posted: t ? t.innerText.trim() : 'No Time'
            };
        });
    }""")
    print("Cards on Worker A's page:")
    for c in cards:
        print(f"  - [{c['posted']}] {c['title'][:40]}")
