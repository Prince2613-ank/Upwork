from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    page = browser.contexts[0].new_page()
    
    for pn in [5, 10, 15, 20, 25, 30, 40, 50, 70, 100]:
        url = f"https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency&page={pn}"
        try:
            page.goto(url, timeout=25000)
            page.wait_for_timeout(2000)
            
            js = """() => {
                const arts = [...document.querySelectorAll('article, [data-test="job-tile"]')];
                if (!arts.length) return null;
                const getP = (a) => {
                    for (const s of a.querySelectorAll('span, small, p')) {
                        const t = (s.innerText || '').trim();
                        if (t.startsWith('Posted ') || t.includes('ago') || t.includes('yesterday')) return t;
                    }
                    return '';
                };
                return {
                    count: arts.length,
                    first: getP(arts[0]),
                    last: getP(arts[arts.length - 1])
                };
            }"""
            res = page.evaluate(js)
            if res:
                print(f"Page {pn:3d} (50 jobs): First = {res['first']:25s} | Last = {res['last']}")
            else:
                print(f"Page {pn:3d}: No jobs found")
        except Exception as e:
            print(f"Page {pn:3d} err: {e}")
            
    page.close()
