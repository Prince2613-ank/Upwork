import sys
from playwright.sync_api import sync_playwright

def inspect():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp("http://[::1]:9223", timeout=10000)
            ctx = browser.contexts[0]
            pages = ctx.pages
            print(f"Chrome Pages count: {len(pages)}")
            for i, pg in enumerate(pages):
                print(f"Page {i}: url={pg.url} title={pg.title()}")
                pg.screenshot(path=f"scratch/chrome_page_{i}.png")
                # print first 500 chars of text
                text = pg.evaluate("document.body ? document.body.innerText.slice(0, 300) : ''")
                print(f"  Content: {repr(text)}")
        except Exception as e:
            print("Chrome error:", e)

if __name__ == "__main__":
    inspect()
