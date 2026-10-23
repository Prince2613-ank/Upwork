import os
import sys
import time
import json
import urllib.request
import subprocess
import win32gui
import win32con

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROFILE_A = os.path.join(USERPROFILE, "chrome_upwork_profile")
PROFILE_B = os.path.join(USERPROFILE, "chrome_upwork_profile_2")

PORT_A = 9222
PORT_B = 9223

LOGIN_URL = "https://www.upwork.com/login"

def kill_port_processes():
    for port in [PORT_A, PORT_B]:
        try:
            cmd = f'powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort {port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"'
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            pids = [p.strip() for p in res.stdout.strip().split() if p.strip()]
            for pid in pids:
                subprocess.run(f"taskkill /PID {pid} /F /T", shell=True, capture_output=True)
        except Exception:
            pass

def bring_window_to_front(port):
    def enum_handler(hwnd, extra):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if "chrome" in title.lower() or "upwork" in title.lower():
                try:
                    win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                    win32gui.SetForegroundWindow(hwnd)
                except Exception:
                    pass
    win32gui.EnumWindows(enum_handler, None)

def check_cdp_status(port):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1.5) as r:
            pages = json.loads(r.read().decode())
            for p in pages:
                if p.get("type") == "page":
                    return p.get("title", ""), p.get("url", "")
            return "Connected", "No active page"
    except Exception:
        return None, None

def main():
    print("=" * 65)
    print("  OPENING BOTH CHROME WINDOWS FOR LIVE USER LOGIN")
    print(f"  Worker A (Chrome 1): Port {PORT_A} | Profile: chrome_upwork_profile")
    print(f"  Worker B (Chrome 2): Port {PORT_B} | Profile: chrome_upwork_profile_2")
    print("=" * 65)

    kill_port_processes()
    time.sleep(1)

    os.makedirs(PROFILE_A, exist_ok=True)
    os.makedirs(PROFILE_B, exist_ok=True)

    # Launch Chrome 1
    print(f"\n[1/2] Opening Chrome 1 on Port {PORT_A} to {LOGIN_URL}...")
    p1 = subprocess.Popen([
        CHROME_EXE,
        f"--remote-debugging-port={PORT_A}",
        f"--user-data-dir={PROFILE_A}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        LOGIN_URL
    ])

    time.sleep(2)

    # Launch Chrome 2
    print(f"[2/2] Opening Chrome 2 on Port {PORT_B} to {LOGIN_URL}...")
    p2 = subprocess.Popen([
        CHROME_EXE,
        f"--remote-debugging-port={PORT_B}",
        f"--user-data-dir={PROFILE_B}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        LOGIN_URL
    ])

    time.sleep(3)

    # Bring both to front
    bring_window_to_front(PORT_A)
    bring_window_to_front(PORT_B)

    print("\n" + "=" * 65)
    print("  BOTH CHROME TABS ARE NOW OPEN ON YOUR SCREEN!")
    print("  Please log into Upwork in BOTH windows.")
    print("  Monitoring login status in real-time below...")
    print("=" * 65 + "\n")

    # Keep both processes alive and monitor login status
    while True:
        t1, u1 = check_cdp_status(PORT_A)
        t2, u2 = check_cdp_status(PORT_B)

        a_logged = False
        b_logged = False

        if u1:
            u1_l = u1.lower()
            if "/nx/search" in u1_l or "/nx/find-work" in u1_l or "dashboard" in u1_l:
                a_logged = True
            elif "/login" not in u1_l and "login" not in t1.lower() and "account-security" not in u1_l:
                a_logged = True

        if u2:
            u2_l = u2.lower()
            if "/nx/search" in u2_l or "/nx/find-work" in u2_l or "dashboard" in u2_l:
                b_logged = True
            elif "/login" not in u2_l and "login" not in t2.lower() and "account-security" not in u2_l:
                b_logged = True

        stat1 = "[LOGGED IN - READY]" if a_logged else f"[WAITING LOGIN: {t1 or 'Opening...'}]"
        stat2 = "[LOGGED IN - READY]" if b_logged else f"[WAITING LOGIN: {t2 or 'Opening...'}]"

        print(f"[LIVE STATUS] Port 9222: {stat1} | Port 9223: {stat2}", flush=True)

        if a_logged and b_logged:
            print("\n*** BOTH PORTS ARE LOGGED IN AND READY TO SCRAPE! ***\n", flush=True)

        time.sleep(4)

if __name__ == "__main__":
    main()
