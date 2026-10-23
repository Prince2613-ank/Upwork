from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = browser.contexts[0].new_page()
    page.goto('https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency&page=1', timeout=30000)
    page.wait_for_timeout(3000)
    
    js = """() => {
        const arts = [...document.querySelectorAll('article, [data-test="job-tile"]')];
        return arts.slice(0, 5).map(a => {
            let posted = '';
            const spans = [...a.querySelectorAll('span, small, p')];
            for (const s of spans) {
                const t = (s.innerText || '').trim();
                if (t.startsWith('Posted ') || t.includes('ago') || t.includes('yesterday')) {
                    posted = t; break;
                }
            }
            const title = a.querySelector('a[href*="/jobs/"]')?.innerText || '';
            return { title: title.trim().substring(0, 30), posted };
        });
    }"""
    cards = page.evaluate(js)
    for c in cards:
        print(f"Title: {c['title'].encode('ascii', 'ignore').decode()} | Posted: {c['posted']}")
    page.close()
