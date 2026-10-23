from playwright.sync_api import sync_playwright
import json

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    print("Page URL:", page.url)
    print("Page Title:", page.title())
    
    data = page.evaluate("""() => {
        const results = [];
        // Look for job links
        const links = document.querySelectorAll('a[href*="/jobs/"]');
        for (let i = 0; i < Math.min(links.length, 5); i++) {
            const l = links[i];
            results.push({
                tag: l.tagName,
                href: l.href,
                text: l.innerText.trim(),
                parentTag: l.parentElement ? l.parentElement.tagName : null,
                outer: l.outerHTML.substring(0, 150)
            });
        }
        return {
            total_job_links: links.length,
            samples: results
        };
    }""")
    print("Extracted:", json.dumps(data, indent=2))
