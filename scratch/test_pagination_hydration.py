from playwright.sync_api import sync_playwright
import sys
import json
import time

sys.stdout.reconfigure(encoding='utf-8')

# Connect to Chrome on 9222 (which has the logged in Upwork session and cookies)
# Let's inspect without disturbing Worker A
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    url = "https://www.upwork.com/jobs/~022112660193329382861/"
    print("Navigating to:", url)
    page.goto(url, wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    # Scroll down to trigger lazy loading of client history
    page.evaluate("""() => {
        let el = document.querySelector('.extra-jobs-cards, [data-qa="client-recent-history"], .client-history');
        if (el) el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        else window.scrollTo(0, 2500);
    }""")
    page.wait_for_timeout(2000)

    # Check what DOM elements exist inside the history card
    res = page.evaluate("""() => {
        let h = Array.from(document.querySelectorAll('*')).find(el => el.innerText && el.innerText.includes("Client's recent history"));
        let card = h ? h.closest('.air3-card') : null;
        if (!card) return { found: false };

        let pag = card.querySelectorAll('ul.air3-pagination, nav, .air3-pagination');
        let allBtns = Array.from(card.querySelectorAll('button, a')).map(b => ({
            tag: b.tagName,
            text: (b.innerText || '').trim(),
            classes: b.className,
            aria: b.getAttribute('aria-label'),
            dataTest: b.getAttribute('data-test')
        }));

        let contractTitles = Array.from(card.querySelectorAll('a[href*="/jobs/"], a.js-job-link')).map(a => a.innerText.trim());

        return {
            found: true,
            header: h.innerText,
            contractsVisible: contractTitles.length,
            contractTitlesSample: contractTitles.slice(0, 10),
            paginationCount: pag.length,
            paginationHTML: Array.from(pag).map(p => p.outerHTML.slice(0, 300)),
            allButtons: allBtns
        };
    }""")

    print(json.dumps(res, indent=2))
    page.close()
