from playwright.sync_api import sync_playwright

for port in [9222, 9223]:
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = b.contexts[0]
            page = ctx.pages[0]
            print(f"Port {port}: Current Page Title: '{page.title()}' | URL: '{page.url}'")
            # Check if there is an avatar or sign-in button
            content = page.content()
            has_login = "login" in page.url.lower() or "log in" in page.title().lower()
            print(f"Port {port}: Needs login? {has_login}")
        except Exception as e:
            print(f"Port {port} error: {e}")
