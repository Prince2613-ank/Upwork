from playwright.sync_api import sync_playwright
import os

with sync_playwright() as pw:
    try:
        browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9223", timeout=10000)
        ctx = browser.contexts[0]
        print(f"Total pages in Edge: {len(ctx.pages)}")
        for i, p in enumerate(ctx.pages):
            try:
                print(f"Page {i}: URL={p.url} | Title={p.title()}")
                if "upwork.com" in p.url:
                    p.screenshot(path="output/edge_stuck_tab.png")
                    print(f"Screenshot saved to output/edge_stuck_tab.png")
            except Exception as pe:
                print(f"Page {i} error: {pe}")
    except Exception as e:
        print("CDP Connect error:", e)
