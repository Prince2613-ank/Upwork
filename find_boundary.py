import urllib.request, json
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp('http://127.0.0.1:9222')
    ctx = browser.contexts[0]
    page = ctx.new_page()
    
    # Check page 1, 5, 10, 15, 20, 25 for Worker A
    COUNTRIES_A = "United%2520States,United%2520Kingdom,Canada,Australia%2520and%2520New%2520Zealand"
    for pn in [1, 5, 10, 15, 20, 25]:
        url = f"https://www.upwork.com/nx/search/jobs?location={COUNTRIES_A}&payment_verified=1&per_page=50&sort=recency&page={pn}"
        page.goto(url, timeout=30000, wait_until="domcontentloaded")
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
        if res:
            print(f"[Worker A] Page {pn:2d}: count={res['count']} | first='{res['first']}' | last='{res['last']}'", flush=True)
            if any(k in (res['first'] + res['last']).lower() for k in ("yesterday", "day ago", "days ago", "sep 27")):
                print(f"[Worker A] Found target date boundary around Page {pn}!", flush=True)
                break
        else:
            print(f"[Worker A] Page {pn:2d}: no cards", flush=True)
            
    page.close()
