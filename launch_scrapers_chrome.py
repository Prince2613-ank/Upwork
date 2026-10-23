import subprocess
import time
import urllib.request
import json
import os

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

def is_port_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False

def launch_chrome_instance(port: int, profile_dir: str):
    if is_port_ready(port):
        print(f"Port {port} is already running.")
        return True
    
    os.makedirs(profile_dir, exist_ok=True)
    args = [
        CHROME_EXE,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile_dir}",
        "--disable-fre",
        "--no-default-browser-check",
        "--no-first-run",
        "--new-window",
        "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"
    ]
    
    # Use DETACHED_PROCESS to keep Chrome alive independently
    DETACHED_PROCESS = 0x00000008
    CREATE_NEW_PROCESS_GROUP = 0x00000200
    subprocess.Popen(args, creationflags=DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP)
    
    for _ in range(8):
        time.sleep(1)
        if is_port_ready(port):
            print(f"Port {port} started successfully!")
            return True
    return False

if __name__ == "__main__":
    p1 = os.path.join(USERPROFILE, "chrome_upwork_profile")
    p2 = os.path.join(USERPROFILE, "chrome_upwork_profile_2")
    
    s1 = launch_chrome_instance(9222, p1)
    s2 = launch_chrome_instance(9223, p2)
    
    print(f"Port 9222 ready: {s1}")
    print(f"Port 9223 ready: {s2}")
