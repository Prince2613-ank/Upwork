from playwright.sync_api import sync_playwright
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    url = "https://www.upwork.com/jobs/~022112658363064905128/?referrer_url_path=%2Fnx%2Fsearch%2Fjobs%2F"
    page.goto(url, wait_until="commit", timeout=30000)
    page.wait_for_timeout(3000)

    print("Title:", page.title())
    print("URL:", page.url)

    res = page.evaluate("""() => {
        let texts = Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6, span, div'))
            .map(e => e.innerText)
            .filter(t => t && t.includes("history"));
        return {
            matchingTexts: texts.slice(0, 10),
            bodyLength: document.body.innerHTML.length
        };
    }""")
    print("Result:", res)
    page.close()
