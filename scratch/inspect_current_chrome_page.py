from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    soup = BeautifulSoup(page.content(), 'html.parser')
    
    for s in soup.find_all(['section', 'div', 'article']):
        h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        if h and "recent history" in h.get_text().lower():
            print("Section tag:", s.name, s.get('class'), s.get('id'))
            print("All links/buttons in this section:")
            for b in s.find_all(['a', 'button']):
                print(" ", b.name, b.get('class'), f"'{b.get_text(strip=True)[:60]}'")
            
            # Find contract items
            items = s.find_all('div', class_=lambda c: c and 'item' in str(c))
            print(f"\nTotal items matching 'item': {len(items)}")
            break
