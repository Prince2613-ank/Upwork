from playwright.sync_api import sync_playwright
import time

def find_day_7():
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = [p for p in context.pages if "upwork.com" in p.url][0]
        
        # Test regional queries
        regions = ["Europe", "United%20Kingdom", "Canada", "Australia%20and%20New%20Zealand"]
        for r in regions:
            # Let's test page 20, 30, 40
            for pg in [15, 25, 35]:
                url = f"https://www.upwork.com/nx/search/jobs/?location={r}&payment_verified=1&per_page=50&sort=recency&page={pg}"
                page.goto(url, timeout=30000)
                time.sleep(3)
                info = page.evaluate("""() => {
                    const cards = document.querySelectorAll('article[data-test="JobTile"]');
                    const dates = [];
                    cards.forEach(c => {
                        const el = c.querySelector('[data-test="job-pubilshed-date"], [data-test="posted-on"], small');
                        if (el) dates.push(el.textContent.trim());
                    });
                    return {
                        count: cards.length,
                        first: dates[0] || 'none',
                        last: dates[dates.length - 1] || 'none'
                    };
                }""")
                print(f"Region {r} Page {pg}: {info}", flush=True)
                if "6 days ago" in str(info) or "7 days ago" in str(info) or "8 days ago" in str(info) or "1 week ago" in str(info):
                    print(f"===> FOUND DAY 7 in {r} at Page {pg}! <===", flush=True)
                    return url

if __name__ == "__main__":
    find_day_7()
