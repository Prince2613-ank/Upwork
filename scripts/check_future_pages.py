import asyncio
from playwright.async_api import async_playwright
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.extraction.search_parser import parse_search_page_html
import csv

with open('output/jobs.csv', 'r', encoding='utf-8-sig') as f:
    jobs = list(csv.DictReader(f))
saved_ids = {j['job_id'] for j in jobs}

async def check_pages():
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        page = [pg for pg in browser.contexts[0].pages if 'nx/search/jobs' in pg.url][0]
        
        for pg_num in [16, 17, 18, 19, 20, 25]:
            url = f'https://www.upwork.com/nx/search/jobs?location=Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,United%2520States%2520Virgin%2520Islands&payment_verified=1&per_page=50&sort=recency&page={pg_num}'
            await page.goto(url)
            await asyncio.sleep(2.5)
            cards = parse_search_page_html(await page.content())
            in_db = sum(1 for c in cards if c.get('job_id') in saved_ids)
            first_time = cards[0].get('posted_time', '') if cards else 'N/A'
            print(f'Page {pg_num}: {len(cards)} cards | {in_db} in DB | {len(cards)-in_db} NEW | First post: {first_time}')

asyncio.run(check_pages())
