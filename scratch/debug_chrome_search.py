from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://[::1]:9223")
    page = browser.contexts[0].pages[0]
    
    console_logs = []
    failed_requests = []
    
    page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
    page.on("requestfailed", lambda req: failed_requests.append(f"{req.url} -> {req.failure}"))
    
    print("Reloading page...")
    try:
        page.reload(wait_until="domcontentloaded", timeout=15000)
    except Exception as e:
        print("Reload err:", e)
        
    import time
    time.sleep(3)
    
    print("=== FAILED REQUESTS ===")
    for fr in failed_requests[:10]:
        print(" ", fr)
        
    print("=== CONSOLE ERRORS ===")
    for cl in console_logs:
        if "error" in cl.lower() or "403" in cl or "429" in cl or "fail" in cl.lower():
            print(" ", cl[:120])
