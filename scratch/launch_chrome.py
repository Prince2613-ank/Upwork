import subprocess, time, os

cmd = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    "--remote-debugging-port=9222",
    r"--user-data-dir=C:\Users\princ\chrome_upwork_profile_2",
    "--disable-fre",
    "--no-default-browser-check",
    "--no-first-run",
    "--new-window",
    "https://www.upwork.com"
]

print("Launching Chrome...")
p = subprocess.Popen(cmd, creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
print("PID:", p.pid)
time.sleep(3)

import urllib.request
try:
    with urllib.request.urlopen("http://127.0.0.1:9222/json/version", timeout=3) as r:
        print("Port 9222 status:", r.status)
except Exception as e:
    print("Port 9222 err:", e)
