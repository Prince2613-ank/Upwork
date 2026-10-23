import urllib.request
import json

try:
    with urllib.request.urlopen("http://127.0.0.1:9223/json", timeout=2) as r:
        pages = json.loads(r.read().decode())
        for p in pages:
            if "upwork" in p.get("url", ""):
                print("Edge Tab:", p.get("title"), "->", p.get("url"))
except Exception as e:
    print("Error:", e)
