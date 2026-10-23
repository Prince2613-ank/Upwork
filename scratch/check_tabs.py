import urllib.request
import json

def dump_tabs(url, name):
    try:
        data = json.loads(urllib.request.urlopen(f"{url}/json", timeout=2).read())
        print(f"=== {name} TABS ===")
        for t in data:
            if t.get("type") == "page":
                print(f"  ID: {t.get('id')} | Title: {t.get('title')[:60]} | URL: {t.get('url')[:80]}")
    except Exception as e:
        print(f"{name} err: {e}")

if __name__ == "__main__":
    dump_tabs("http://127.0.0.1:9222", "Chrome (9222)")
    dump_tabs("http://127.0.0.1:9223", "Edge (9223)")
