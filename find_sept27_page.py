from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = browser.contexts[0].new_page()
    
    for pn in [10, 20, 30, 40, 50, 60, 70, 80, 100]:
        url = f"https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency&page={pn}"
        page.goto(url, timeout=30000)
        page.wait_for_timeout(2500)
        
        js = """() => {
            const arts = [...document.querySelectorAll('article, [data-test="job-tile"]')];
            if (!arts.length) return {count: 0};
            const dates = [];
            for (const a of arts) {
                const spans = [...a.querySelectorAll('span, small, p')];
                for (const s of spans) {
                    const txt = (s.innerText || '').trim();
                    if (txt.startsWith('Posted ') || txt.includes('ago') || txt.includes('yesterday')) {
                        dates.push(txt);
                        break;
                    }
                }
            }
            return {count: arts.length, first: dates[0] || '', last: dates[dates.length - 1] || ''};
        }"""
        res = page.evaluate(js)
        print(f"Page {pn:3d}: count={res.get('count')} | first={res.get('first')} | last={res.get('last')}")
        first_txt = res.get('first', '').lower()
        if 'yesterday' in first_txt or 'day ago' in first_txt or 'days ago' in first_txt or 'sep' in first_txt:
            print(f"==> Sept 27 or older starts around page {pn}!")
            break
            
    page.close()
