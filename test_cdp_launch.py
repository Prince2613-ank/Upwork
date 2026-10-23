import subprocess
import time
import urllib.request
import json
from pathlib import Path

chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile = r"C:\Users\princ\chrome_upwork_profile"
args = [
    chrome_exe,
    "--remote-debugging-port=9222",
    f"--user-data-dir={profile}",
    "--disable-fre",
    "--no-default-browser-check",
    "--no-first-run",
    "--new-window",
    "https://www.upwork.com"
]

print("Launching Chrome on 9222...")
p = subprocess.Popen(args)
print(f"PID: {p.pid}")

online = False
for i in range(8):
    time.sleep(1)
    try:
        with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=1.5) as r:
            data = json.loads(r.read().decode())
            browser = data.get("Browser")
            print(f"[SUCCESS] Port 9222 is ONLINE: {browser}")
            online = True
            break
    except Exception as e:
        print(f"Attempt {i+1} failed: {e}")

if not online:
    print("Failed to connect to 9222")
