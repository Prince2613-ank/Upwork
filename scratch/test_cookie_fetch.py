import urllib.request
from playwright.sync_api import sync_playwright

def test():
    try:
        with sync_playwright() as p:
            b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
            ctx = b.contexts[0]
            cookies = ctx.cookies()
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            ua = ctx.pages[0].evaluate("navigator.userAgent")
            print("Cookies count:", len(cookies))
            req = urllib.request.Request(
                "https://www.upwork.com/jobs/~022111340031676775865/",
                headers={
                    "User-Agent": ua,
                    "Cookie": cookie_str,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9"
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")
                print("HTTP SUCCESS! Status:", resp.status, "Len:", len(raw_html), "Has NUXT:", "__NUXT_DATA__" in raw_html)
    except Exception as e:
        print("HTTP err:", e)

if __name__ == "__main__":
    test()
