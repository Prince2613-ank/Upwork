import threading
from playwright.sync_api import sync_playwright

def worker(worker_id, port):
    with sync_playwright() as p:
        b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
        ctx = b.contexts[0]
        page = ctx.new_page()
        page.goto("https://www.google.com", timeout=10000, wait_until="commit")
        title = page.title()
        print(f"Worker {worker_id} on port {port} success: {title}")
        page.close()

t1 = threading.Thread(target=worker, args=("A1", 9222))
t2 = threading.Thread(target=worker, args=("A2", 9222))
t1.start()
t2.start()
t1.join()
t2.join()
print("All concurrent workers finished successfully!")
