import time
from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

url = "https://www.upwork.com/jobs/~022111886000493967691/"

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    
    print(f"Navigating to {url}...")
    page.goto(url, wait_until="domcontentloaded")
    time.sleep(3)
    
    # 1. Expand all 'View more' in client history
    for _ in range(5):
        vm_btn = page.query_selector('[data-test="client-history"] a:has-text("View more"), .client-history a:has-text("View more"), a.up-n-link:has-text("View more")')
        if vm_btn and vm_btn.is_visible():
            print("Found 'View more' button! Clicking it...")
            vm_btn.click()
            time.sleep(2)
        else:
            print("No more 'View more' button visible.")
            break
            
    # 2. Expand all 'more' text truncation buttons in client history
    more_btns = page.query_selector_all('[data-test="client-history"] button.air3-truncation-btn, .client-history button.air3-truncation-btn')
    print(f"Found {len(more_btns)} 'more' truncation buttons in client history!")
    for mb in more_btns:
        try:
            if mb.is_visible() and "more" in mb.inner_text().lower():
                mb.click()
                time.sleep(0.2)
        except Exception as e:
            pass
            
    content = page.content()
    soup = BeautifulSoup(content, 'html.parser')
    sec = soup.select_one('[data-test="client-history"], [data-test="contract-history"], .client-history, #client-history')
    items = sec.select('div.item[data-cy="job"]') if sec else []
    print(f"Total history items after expansion: {len(items)}")
    
    for idx, it in enumerate(items):
        title = it.select_one('a.js-job-link')
        t_text = title.get_text(strip=True) if title else "No Title"
        main_div = it.select_one('.main')
        print(f"\n--- Item {idx+1}: {t_text} ---")
        for child in main_div.children:
            if child.name:
                text = child.get_text(" ", strip=True)
                if "to freelancer" in text.lower():
                    pass # client to freelancer
                else:
                    print(f"  FREELANCER REVIEW: {text}")
