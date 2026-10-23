from playwright.sync_api import sync_playwright
import sys
import json
import time

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    url = "https://www.upwork.com/jobs/~022112660193329382861/?referrer_url_path=%2Fnx%2Fsearch%2Fjobs%2F"
    page.goto(url, wait_until="commit", timeout=30000)
    page.wait_for_timeout(3000)

    # Scroll to history card
    page.evaluate("""() => {
        let el = document.querySelector('.extra-jobs-cards');
        if (el) el.scrollIntoView();
    }""")
    page.wait_for_timeout(1000)

    # Count contracts before clicking
    before_cnt = page.evaluate("() => document.querySelectorAll('.extra-jobs-cards a.js-job-link').length")
    print(f"Contracts before clicking 'View more': {before_cnt}")

    # Now click "View more" repeatedly until all contracts are loaded!
    clicks = 0
    while clicks < 10:
        has_more = page.evaluate("""() => {
            let links = Array.from(document.querySelectorAll('.extra-jobs-cards a, .extra-jobs-cards button'));
            let vm = links.find(a => (a.innerText || '').trim().toLowerCase() === 'view more');
            if (vm) {
                vm.click();
                return true;
            }
            return false;
        }""")
        if not has_more:
            print(f"No more 'View more' link found after {clicks} clicks.")
            break
        clicks += 1
        page.wait_for_timeout(1500)
        cnt = page.evaluate("() => document.querySelectorAll('.extra-jobs-cards a.js-job-link').length")
        print(f"Click #{clicks}: now {cnt} contracts visible")

    # Also expand all 'more' truncation buttons
    more_clicked = page.evaluate("""() => {
        let btns = Array.from(document.querySelectorAll('.extra-jobs-cards button.air3-truncation-btn'));
        let clicked = 0;
        btns.forEach(b => {
            if ((b.innerText || '').trim().toLowerCase() === 'more') {
                try { b.click(); clicked++; } catch(e) {}
            }
        });
        return clicked;
    }""")
    print(f"Expanded {more_clicked} truncation 'more' buttons.")

    final_cnt = page.evaluate("() => document.querySelectorAll('.extra-jobs-cards a.js-job-link').length")
    print(f"FINAL CONTRACTS LOADED: {final_cnt}")

    page.close()
