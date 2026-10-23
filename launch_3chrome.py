"""
Launch 3 Chrome instances for parallel Upwork collection.
Ensures Chrome is running on ports 9222, 9223, and 9224.
"""

import os
import sys
import time
import subprocess
import urllib.request
from pathlib import Path

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.join(os.environ.get("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
]

def find_chrome() -> str:
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Could not find chrome.exe on system.")

def is_port_ready(port: int) -> bool:
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5)
        return True
    except Exception:
        return False

def launch_chrome(chrome_exe: str, port: int, profile_name: str, url: str):
    profile_dir = os.path.join(USERPROFILE, profile_name)
    os.makedirs(profile_dir, exist_ok=True)

    if is_port_ready(port):
        print(f"  [Port {port}] Chrome is ALREADY running and ready! (Profile: {profile_name})")
        return None

    cmd = f'start "" "{chrome_exe}" --remote-debugging-port={port} --user-data-dir="{profile_dir}" --no-first-run --no-default-browser-check "{url}"'

    print(f"  [Port {port}] Launching Chrome with profile '{profile_name}'...")
    proc = subprocess.Popen(cmd, shell=True)
    return proc

def main():
    print("=" * 60)
    print("  FLODATA MULTI-CHROME LAUNCHER (3x SPEED)")
    print("=" * 60)
    print()

    chrome_exe = find_chrome()
    print(f"Found Chrome: {chrome_exe}")
    print()

    search_url = "https://www.upwork.com/nx/search/jobs?payment_verified=1&per_page=50&sort=recency"

    configs = [
        (9222, "chrome_upwork_profile", search_url),
        (9223, "chrome_upwork_profile_2", search_url),
        (9224, "chrome_upwork_profile_3", search_url),
    ]

    for port, prof, url in configs:
        launch_chrome(chrome_exe, port, prof, url)
        time.sleep(1)

    print()
    print("Verifying Chrome instances...")
    all_ready = True
    for port, prof, _ in configs:
        ready = False
        for _ in range(5):
            if is_port_ready(port):
                ready = True
                break
            time.sleep(1)
        if ready:
            print(f"  [OK] Port {port}: READY")
        else:
            print(f"  [FAIL] Port {port}: NOT RESPONDING")
            all_ready = False

    print()
    print("=" * 60)
    if all_ready:
        print("  ALL 3 CHROME INSTANCES ARE READY!")
        print("  1. Ensure you are logged into Upwork in all 3 Chrome windows.")
        print("  2. Run: python run_parallel.py")
    else:
        print("  Some Chrome instances did not respond. Check if Chrome blocked startup.")
    print("=" * 60)

if __name__ == "__main__":
    main()
