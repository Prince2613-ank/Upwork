import asyncio
from playwright.async_api import async_playwright

async def inspect_search():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://localhost:9222')
        context = browser.contexts[0]
        page = context.pages[0] if context.pages else await context.new_page()
        
        url = 'https://www.upwork.com/nx/search/jobs/?sort=recency'
        print('Navigating to:', url)
        await page.goto(url, wait_until='domcontentloaded', timeout=30000)
        await asyncio.sleep(4)
        
        cards_info = await page.evaluate('''() => {
            const tiles = document.querySelectorAll('article, [data-test="JobTile"]');
            return Array.from(tiles).slice(0, 8).map(t => {
                const titleEl = t.querySelector('[data-test="job-tile-title-link"], [data-test="UpLink"]');
                const timeEl = t.querySelector('[data-test="posted-on"], small');
                return {
                    title: titleEl ? titleEl.innerText.trim() : 'no title',
                    time: timeEl ? timeEl.innerText.trim() : 'no time'
                };
            });
        }''')
        for i, c in enumerate(cards_info):
            print(f"{i+1}. {c['title']} | {c['time']}")

asyncio.run(inspect_search())
