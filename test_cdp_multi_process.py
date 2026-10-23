import multiprocessing
import time
from playwright.sync_api import sync_playwright

def worker(worker_id):
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    context = browser.contexts[0]
    page = context.new_page()
    try:
        url = f"https://httpbin.org/get?worker={worker_id}"
        print(f"[Worker {worker_id}] Navigating to {url}...")
        page.goto(url, timeout=15000)
        title = page.title()
        print(f"[Worker {worker_id}] SUCCESS! Page title: {title}")
        time.sleep(2)
    finally:
        page.close()
        p.stop()

if __name__ == "__main__":
    p1 = multiprocessing.Process(target=worker, args=(1,))
    p2 = multiprocessing.Process(target=worker, args=(2,))
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    print("Multi-process CDP test finished!")
