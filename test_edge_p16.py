from playwright.sync_api import sync_playwright

COUNTRIES_B = "Europe,India,United%2520Arab%2520Emirates,Saudi%2520Arabia"
with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223")
    page = browser.contexts[0].new_page()
    for pn in [4, 6, 8, 10]:
        page.goto(f"https://www.upwork.com/nx/search/jobs?location={COUNTRIES_B}&payment_verified=1&per_page=50&sort=recency&page={pn}", timeout=25000, wait_until="domcontentloaded")
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
            return { count: arts.length, first: getP(arts[0]), last: getP(arts[arts.length - 1]) };
        }"""
        res = page.evaluate(js)
        print(f"[Worker B] Page {pn}: {res}", flush=True)
    page.close()
