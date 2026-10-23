from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = browser.contexts[0].new_page()
    page.goto('https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=10&sort=recency', timeout=30000)
    page.wait_for_timeout(3000)
    
    js = """() => {
        const arts = [...document.querySelectorAll('article, [data-test="job-tile"]')];
        if (!arts.length) return 'No article found';
        const art = arts[0];
        const times = [...art.querySelectorAll('*')].filter(el => {
            const t = (el.innerText || '').toLowerCase();
            return (t.includes('ago') || t.includes('yesterday') || t.includes('posted')) && el.children.length === 0;
        }).map(el => ({ tag: el.tagName, class: el.className, text: el.innerText, dataTest: el.getAttribute('data-test') }));
        return {
            title: art.querySelector('a[href*="/jobs/"]')?.innerText || '',
            times: times,
            allText: art.innerText.split('\\n').slice(0, 8)
        };
    }"""
    res = page.evaluate(js)
    print("Found:", res)
    page.close()
