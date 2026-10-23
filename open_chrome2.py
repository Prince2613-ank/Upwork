import os
import time
import urllib.request
import json
import subprocess

profile = r"C:\Users\princ\.gemini\antigravity-browser-profile-2"
os.makedirs(profile, exist_ok=True)

chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
args = [
    chrome_exe,
    "--remote-debugging-port=9223",
    f"--user-data-dir={profile}",
    "--disable-fre",
    "--no-default-browser-check",
    "--no-first-run",
    "--new-window",
    "https://www.upwork.com"
]

print("Launching 2nd Chrome on Port 9223...")
proc = subprocess.Popen(args)
print(f"Launched Chrome 2 process PID: {proc.pid}")

# Wait for CDP to become ready
for i in range(10):
    try:
        with urllib.request.urlopen("http://127.0.0.1:9223/json/version", timeout=1.5) as r:
            data = json.loads(r.read().decode())
            print(f"[SUCCESS] Chrome 2 is ONLINE on port 9223! ({data.get('Browser')})")
            break
    except Exception as e:
        time.sleep(1)

# Keep Chrome alive indefinitely
proc.wait()
