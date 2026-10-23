import asyncio
from playwright.async_api import async_playwright

async def inspect():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        context = browser.contexts[0]
        page = None
        for pg in context.pages:
            if "nx/search/jobs" in pg.url:
                page = pg
                break
        if not page:
            print("No active search tab found.")
            return

        print("Page URL:", page.url)
        print("Page Title:", await page.title())

        info = await page.evaluate("""() => {
            const body = document.body.innerText;
            const match = body.match(/([0-9,]+)\\s+jobs\\s+found/i);
            const tiles = document.querySelectorAll('article, [data-test="job-tile"], [data-qa="job-tile"]');
            
            // Extract dates of first 3 and last 3 jobs on current page
            const dates = [];
            document.querySelectorAll('[data-test="posted-on"], [data-test="job-pubilshed-date"], span').forEach(el => {
                const txt = el.innerText ? el.innerText.trim() : '';
                if (txt.match(/posted\\s+\\d+|yesterday|\\d+\\s+(hour|day|week|month)s?\\s+ago/i)) {
                    dates.push(txt);
                }
            });

            return {
                totalFound: match ? match[0] : 'Not found',
                tileCount: tiles.length,
                sampleDates: dates.slice(0, 10)
            };
        }""")
        print("Inspection Results:", info)

asyncio.run(inspect())
