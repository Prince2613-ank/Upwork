import time
from playwright.sync_api import sync_playwright

def inspect():
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = [p for p in context.pages if "upwork.com" in p.url][0]

        for pg in [95, 96, 97, 98, 99]:
            url = (
                "https://www.upwork.com/nx/search/jobs?"
                "location=Europe,Australia%20and%20New%20Zealand,American%20Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%20Islands,Hong%20Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%20Zealand,Qatar,Saudi%20Arabia,Singapore,South%20Korea,United%20Arab%20Emirates,United%20Kingdom,United%20States,United%20States%20Minor%20Outlying%20Islands,United%20States%20Virgin%20Islands"
                f"&payment_verified=1&per_page=50&sort=recency&page={pg}"
            )
            page.goto(url, timeout=30000)
            time.sleep(3)
            info = page.evaluate("""() => {
                const cards = document.querySelectorAll('article[data-test="JobTile"]');
                const dates = [];
                cards.forEach(c => {
                    const postedEl = c.querySelector('[data-test="job-pubilshed-date"], [data-test="posted-on"], small');
                    if (postedEl) dates.push(postedEl.textContent.trim());
                });
                return {
                    count: cards.length,
                    first: dates[0] || 'none',
                    last: dates[dates.length - 1] || 'none'
                };
            }""")
            print(f"Page {pg}: {info}")

if __name__ == "__main__":
    inspect()
