import subprocess
import os
import urllib.request
import time

userprofile = os.environ["USERPROFILE"]
chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
profile_2 = os.path.join(userprofile, "chrome_upwork_profile_2")
os.makedirs(profile_2, exist_ok=True)

args = [
    chrome_exe,
    "--remote-debugging-port=9223",
    f"--user-data-dir={profile_2}",
    "--no-first-run",
    "--no-default-browser-check",
    "https://www.upwork.com"
]

print("Launching Chrome on 9223...")
proc = subprocess.Popen(args)
print(f"Process PID: {proc.pid}")

for i in range(10):
    time.sleep(1)
    try:
        urllib.request.urlopen("http://127.0.0.1:9223/json", timeout=1)
        print("SUCCESS! Chrome on 9223 is ready!")
        break
    except Exception as e:
        print(f"Attempt {i+1}: not ready yet ({e})")
