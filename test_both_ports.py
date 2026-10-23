import subprocess
import time
import os
import urllib.request
import json

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

SEARCH_URL = (
    "https://www.upwork.com/nx/search/jobs?"
    "location=Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,"
    "Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,"
    "United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,"
    "United%2520States%2520Virgin%2520Islands&payment_verified=1&per_page=50&sort=recency"
)

procs = []
for port, prof in [(9222, "chrome_upwork_profile"), (9223, "chrome_upwork_profile_2")]:
    p_dir = os.path.join(USERPROFILE, prof)
    args = [
        CHROME_EXE,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={p_dir}",
        "--disable-fre",
        "--no-default-browser-check",
        "--no-first-run",
        SEARCH_URL
    ]
    print(f"Launching Chrome on Port {port}...")
    p = subprocess.Popen(args)
    procs.append((port, p))

time.sleep(4)

for port, p in procs:
    ready = False
    for _ in range(10):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
                if r.status == 200:
                    d = json.loads(r.read().decode())
                    print(f"Port {port} is READY! Browser: {d.get('Browser')}")
                    ready = True
                    break
        except Exception:
            time.sleep(1)
    if not ready:
        print(f"Port {port} FAILED to respond!")

for port, p in procs:
    try:
        p.terminate()
        p.wait(timeout=2)
    except Exception:
        pass
