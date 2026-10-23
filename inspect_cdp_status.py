import urllib.request
import json

for port in [9222, 9223]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list") as res:
            tabs = json.loads(res.read().decode())
            print(f"=== PORT {port} TABS ({len(tabs)}) ===")
            for t in tabs:
                if t.get("type") == "page":
                    title = t.get("title", "")
                    url = t.get("url", "")
                    print(f"  Title: {title[:60]} | URL: {url[:80]}")
    except Exception as e:
        print(f"Port {port} error: {e}")
