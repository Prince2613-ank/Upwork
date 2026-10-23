import urllib.request
import json

# Close the stuck Upwork tab in Edge via CDP HTTP API
try:
    with urllib.request.urlopen("http://127.0.0.1:9223/json", timeout=5) as r:
        tabs = json.loads(r.read())
        for t in tabs:
            if "upwork.com" in t.get("url", ""):
                tid = t.get("id")
                print(f"Closing stuck tab {tid}...")
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:9223/json/close/{tid}") as cr:
                        print("Closed:", cr.read().decode())
                except Exception as ce:
                    print("Close error:", ce)

    # Open a clean new tab
    with urllib.request.urlopen("http://127.0.0.1:9223/json/new?https://www.upwork.com") as nr:
        print("Opened new clean Upwork tab:", nr.read().decode()[:80])

except Exception as e:
    print("Reset error:", e)
