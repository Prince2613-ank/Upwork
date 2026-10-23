from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    
    # Click all "more" buttons via page.evaluate
    clicked_count = page.evaluate("""() => {
        let count = 0;
        const buttons = document.querySelectorAll('.extra-jobs-cards button.air3-truncation-btn');
        buttons.forEach(btn => {
            if (btn.innerText.toLowerCase().includes('more')) {
                btn.click();
                count++;
            }
        });
        return count;
    }""")
    print(f"Clicked {clicked_count} 'more' buttons via JavaScript!")
    
    # Now inspect the items
    soup = BeautifulSoup(page.content(), 'html.parser')
    sec = soup.select_one('div.extra-jobs-cards')
    items = sec.select('div.item[data-cy="job"]')
    print(f"Total items in extra-jobs-cards: {len(items)}")
    
    for idx, it in enumerate(items):
        title = it.select_one('a.js-job-link')
        t_text = title.get_text(strip=True) if title else "No Title"
        main_div = it.select_one('.main')
        print(f"\n--- Contract {idx+1}: {t_text} ---")
        
        # In Upwork's markup:
        # First child is title span.
        # Second child (if freelancer left rating/feedback) is div.text-body-sm with the freelancer's review of the client!
        # Third child is div.text-body-sm starting with 'To freelancer:' (client's review of freelancer).
        fl_review_text = ""
        for child in main_div.children:
            if not child.name: continue
            text = child.get_text(" ", strip=True)
            if "to freelancer" in text.lower():
                continue # Skip client's feedback to freelancer
            if text and text != t_text:
                # Remove any star rating text prefix like "Rating is 5.0 out of 5. 5.0 5.00 stars"
                clean_text = text
                for prefix in ["rating is", "stars"]:
                    # Clean up rating text
                    pass
                fl_review_text = text
                
        print(f"  FREELANCER FEEDBACK TO CLIENT: {fl_review_text}")
