from playwright.sync_api import sync_playwright
import time

def test_cards():
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        pg = b.contexts[0].pages[0]
        url = "https://www.upwork.com/nx/search/jobs?location=Japan&per_page=50&sort=recency"
        print("Navigating to Japan search on Chrome...")
        pg.goto(url, wait_until="domcontentloaded")
        time.sleep(3)
        cnt = pg.evaluate("""() => {
            const arts = [...document.querySelectorAll('article, li[data-test], [data-test="job-tile"]')];
            return arts.filter(a => a.querySelector('a[href*="/jobs/"]')).length;
        }""")
        print("Cards found on Chrome 9222:", cnt)
        
        # Also test Edge
        b2 = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
        pg2 = b2.contexts[0].pages[0]
        url2 = "https://www.upwork.com/nx/search/jobs?location=Singapore&per_page=50&sort=recency"
        print("Navigating to Singapore search on Edge...")
        pg2.goto(url2, wait_until="domcontentloaded")
        time.sleep(3)
        cnt2 = pg2.evaluate("""() => {
            const arts = [...document.querySelectorAll('article, li[data-test], [data-test="job-tile"]')];
            return arts.filter(a => a.querySelector('a[href*="/jobs/"]')).length;
        }""")
        print("Cards found on Edge 9223:", cnt2)

if __name__ == "__main__":
    test_cards()
