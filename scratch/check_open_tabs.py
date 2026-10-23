import urllib.request
import json

for p in [9222, 9223]:
    try:
        tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{p}/json/list", timeout=3).read().decode())
        print(f"Port {p} has {len(tabs)} tabs:")
        for t in tabs:
            if t.get("type") == "page":
                print(f"  - Title: {t.get('title')}")
                print(f"    URL:   {t.get('url')}")
    except Exception as e:
        print(f"Port {p} error: {e}")
