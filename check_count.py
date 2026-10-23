import asyncio, re
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup

async def test():
    async with async_playwright() as p:
        b = await p.chromium.connect_over_cdp("http://127.0.0.1:9222")
        page = b.contexts[0].pages[0]
        html = await page.content()
        m = re.search(r"([\d,]+)\s+jobs\s+found", html, re.I)
        if m:
            print("Upwork reported:", m.group(0))
        else:
            soup = BeautifulSoup(html, "html.parser")
            h = soup.find(lambda e: e.name in ["h1", "h2", "h3", "div"] and "jobs found" in e.get_text().lower())
            print("Found header:", h.get_text().strip() if h else "Not found")
        await b.close()

asyncio.run(test())
