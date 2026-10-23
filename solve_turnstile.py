from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.pages[0]
    print("Initial Title:", page.title())

    # Check frames for turnstile
    cleared = False
    for attempt in range(15):
        t = page.title().lower()
        if "just a moment" not in t:
            print("Cleared! Page title:", page.title())
            cleared = True
            break
        
        for f in page.frames:
            try:
                btn = f.locator("input[type='checkbox'], #challenge-stage, .ctp-checkbox-label, div[id*='turnstile']")
                if btn.count() > 0:
                    print("Found turnstile widget, attempting click...")
                    btn.first.click(force=True)
                    time.sleep(2)
            except Exception:
                pass
        time.sleep(2)

    if not cleared:
        print("Final Title:", page.title())
        # Try reloading the page
        print("Reloading page...")
        page.reload(wait_until="domcontentloaded")
        time.sleep(3)
        print("Post-reload title:", page.title())
