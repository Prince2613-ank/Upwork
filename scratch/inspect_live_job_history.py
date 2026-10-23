import asyncio
from playwright.sync_api import sync_playwright
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    # Connect to Chrome on 9222
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()
    page.goto("https://www.upwork.com/jobs/~022112658363064905128/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Scroll down to ensure history loads
    page.evaluate("window.scrollTo(0, 1500)")
    page.wait_for_timeout(2000)

    res = page.evaluate("""() => {
        // Find header containing Client's recent history
        let headings = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, div, span'));
        let h = headings.find(el => el.innerText && el.innerText.includes("Client's recent history"));
        let container = h ? h.closest('section, div.air3-card, [data-qa="client-recent-history"], [data-test="client-history"]') : null;
        
        let info = {
            headerFound: !!h,
            headerText: h ? h.innerText : null,
            containerTag: container ? container.tagName : null,
            containerClass: container ? container.className : null,
        };

        if (container) {
            // Find all buttons, links, pagination in this container
            info.buttons = Array.from(container.querySelectorAll('button, a')).map(b => ({
                tag: b.tagName,
                text: b.innerText,
                classes: b.className,
                aria: b.getAttribute('aria-label'),
                dataTest: b.getAttribute('data-test')
            }));

            // Find all list items / child contract items
            let items = container.querySelectorAll('.air3-card-section, section, [data-test="history-item"], li');
            info.itemsCount = items.length;
            info.itemsTextSample = Array.from(items).slice(0, 8).map(it => it.innerText.slice(0, 80));
        }

        // Also check anywhere on page for pagination
        let pag = document.querySelectorAll('ul.air3-pagination, nav[aria-label*="pagination"], .air3-pagination');
        info.pagePagination = Array.from(pag).map(p => ({
            html: p.outerHTML.slice(0, 300),
            buttons: Array.from(p.querySelectorAll('button, a')).map(b => b.innerText)
        }));

        return info;
    }""")

    print(json.dumps(res, indent=2))
    page.close()
