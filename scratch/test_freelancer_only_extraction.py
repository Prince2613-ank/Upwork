from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0]
    soup = BeautifulSoup(page.content(), 'html.parser')
    sec = soup.select_one('div.extra-jobs-cards')
    items = sec.select('div.item[data-cy="job"]')
    
    for idx, it in enumerate(items):
        title = it.select_one('a.js-job-link')
        t_text = title.get_text(strip=True) if title else "No Title"
        main_div = it.select_one('.main')
        
        freelancer_feedback = "No feedback given"
        # Find all direct child divs in main
        child_divs = [c for c in main_div.children if c.name == 'div']
        for c in child_divs:
            c_text = c.get_text(" ", strip=True)
            if "to freelancer" in c_text.lower():
                # This is client's feedback to freelancer - IGNORE!
                continue
            
            # This is freelancer's feedback to client!
            # Look for the air3-truncation span inside this div
            trunc_span = c.select_one('span[id^="air3-truncation-"]')
            if trunc_span:
                # Remove buttons like 'more', 'less'
                for b in trunc_span.find_all(['button', 'a']):
                    b.decompose()
                t = trunc_span.get_text(" ", strip=True)
                if t:
                    freelancer_feedback = t
            elif "no feedback given" in c_text.lower():
                freelancer_feedback = "No feedback given"
                
        print(f"Contract #{idx+1} '{t_text}':")
        print(f"   => Verified Freelancer Review for Client: \"{freelancer_feedback}\"")
