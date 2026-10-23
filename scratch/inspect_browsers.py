import urllib.request
import json

def inspect(name, url):
    print(f"=== {name} ({url}) ===")
    try:
        req = urllib.request.urlopen(f"{url}/json/list", timeout=3)
        tabs = json.loads(req.read().decode())
        pages = [t for t in tabs if t.get("type") == "page"]
        print(f"Found {len(pages)} page(s):")
        for i, p in enumerate(pages):
            t_str = str(p.get('title') or '').encode('ascii', 'replace').decode('ascii')
            u_str = str(p.get('url') or '')
            print(f"  [{i}] Title: {t_str[:60]}")
            print(f"      URL:   {u_str[:90]}")
    except Exception as e:
        print(f"  Failed to connect: {e}")

inspect("Edge (Port 9223 IPv4)", "http://127.0.0.1:9223")
inspect("Chrome (Port 9223 IPv6)", "http://[::1]:9223")
inspect("Chrome (Port 9222 IPv4)", "http://127.0.0.1:9222")
