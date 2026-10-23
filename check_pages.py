import asyncio
from playwright.async_api import async_playwright
from collector.extraction.search_parser import parse_search_page_html
from collector.config.settings import settings

async def test():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = b.contexts[0].pages[0]
        for pg in [1, 5, 20, 50]:
            url = settings.build_search_url(page=pg)
            await page.goto(url, timeout=20000)
            await page.wait_for_timeout(2500)
            cards = parse_search_page_html(await page.content())
            if cards:
                print(f"Page {pg}: {len(cards)} cards. First: '{cards[0].get('job_title')[:30]}' | Posted: '{cards[0].get('posted_time')}' | Last: '{cards[-1].get('posted_time')}'")
            else:
                print(f"Page {pg}: 0 cards found")
        await b.close()

asyncio.run(test())
