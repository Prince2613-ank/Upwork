import sys, os, time
sys.stdout.reconfigure(encoding='utf-8')
sys.path.insert(0, os.path.abspath('.'))

from playwright.sync_api import sync_playwright
from run_daily_system import COMBINED_SEARCH_URL, extract_search_cards

def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp('http://localhost:9222')
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else context.new_page()

        for pn in [55, 60, 65, 70]:
            url = f"{COMBINED_SEARCH_URL}&page={pn}"
            print(f"\n--- Checking Page {pn} ---", flush=True)
            page.goto(url, wait_until='domcontentloaded', timeout=30000)
            time.sleep(2.0)
            cards = extract_search_cards(page)
            print(f"Page {pn}: Found {len(cards)} cards", flush=True)
            if cards:
                print(f"  First: {cards[0].get('posted_raw')} | {cards[0].get('job_title')[:35]}", flush=True)
                print(f"  Last:  {cards[-1].get('posted_raw')} | {cards[-1].get('job_title')[:35]}", flush=True)

if __name__ == '__main__':
    main()
