from playwright.sync_api import sync_playwright
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    url = "https://www.upwork.com/jobs/~022112660193329382861/?referrer_url_path=%2Fnx%2Fsearch%2Fjobs%2F"
    page.goto(url, wait_until="commit", timeout=30000)
    page.wait_for_timeout(3500)

    res = page.evaluate("""() => {
        // Find Client's recent history section
        let h = Array.from(document.querySelectorAll('h5, span, header')).find(e => (e.innerText || '').includes("Client's recent history"));
        let card = h ? h.closest('.air3-card') : null;
        if (!card) return { found: false };

        // Scroll to card
        card.scrollIntoView();

        // Check for pagination
        let pag = card.querySelectorAll('.air3-pagination, ul.air3-pagination, nav[aria-label*="pagination"]');
        let btns = Array.from(card.querySelectorAll('button, a')).map(b => ({
            tag: b.tagName,
            text: (b.innerText || '').trim(),
            classes: b.className,
            aria: b.getAttribute('aria-label')
        }));

        let contracts = Array.from(card.querySelectorAll('.air3-card-section, .items > div, section')).length;

        return {
            found: true,
            headerText: h.innerText,
            cardClasses: card.className,
            paginationFound: pag.length,
            paginationHTML: Array.from(pag).map(p => p.outerHTML),
            allButtons: btns
        };
    }""")

    print(json.dumps(res, indent=2))
    page.close()
