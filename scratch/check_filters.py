import sys
from playwright.sync_api import sync_playwright

def check_filters():
    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = [p for p in context.pages if "upwork.com" in p.url][0]
        page.goto("https://www.upwork.com/nx/search/jobs/?sort=recency", timeout=30000)
        page.wait_for_load_state("domcontentloaded")
        
        # Check all filter headings / labels on the left sidebar
        filters = page.evaluate("""() => {
            const headings = Array.from(document.querySelectorAll('h3, h4, [data-test="filter-title"], .air3-dropdown-toggle, .air3-radio-label, label'));
            return headings.map(h => h.textContent.trim()).filter(t => t.length > 0 && t.length < 40).slice(0, 50);
        }""")
        print("Available filters on page:", filters, flush=True)

if __name__ == "__main__":
    check_filters()
