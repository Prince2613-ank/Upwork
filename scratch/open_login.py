from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.upwork.com/ab/account-security/login"

def open_login(port, name):
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=10000)
            ctx = browser.contexts[0]
            # Use active page or open new page
            pages = ctx.pages
            page = pages[0] if pages else ctx.new_page()
            page.bring_to_front()
            print(f"[{name} - Port {port}] Navigating to {LOGIN_URL}...")
            page.goto(LOGIN_URL, timeout=30000)
            print(f"[{name} - Port {port}] Ready at: {page.url}")
            browser.close()
    except Exception as e:
        print(f"[{name} - Port {port}] Error: {e}")

if __name__ == "__main__":
    print("Opening Upwork Login on both browsers...")
    open_login(9222, "Chrome")
    open_login(9223, "Edge")
    print("Done! Both browsers are ready for login.")
