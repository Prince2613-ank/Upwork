import os
import sys
import time
import json
import urllib.request
import subprocess
import ctypes
import win32gui
import win32con
import win32process
import psutil

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

PROFILE_A = os.path.join(USERPROFILE, "chrome_upwork_profile")
PROFILE_B = os.path.join(USERPROFILE, "chrome_upwork_profile_2")

PORT_A = 9222
PORT_B = 9223

LOGIN_URL = "https://www.upwork.com/login"

def kill_debug_chromes():
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'chrome' in p.name().lower():
                cmd = p.cmdline()
                if any('remote-debugging-port' in a for a in cmd):
                    p.kill()
        except Exception:
            pass
    time.sleep(1)

def get_screen_resolution():
    user32 = ctypes.windll.user32
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def force_window_to_front(hwnd, x, y, w, h):
    try:
        # Allow foreground changes
        ctypes.windll.user32.AllowSetForegroundWindow(-1)
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        # Position window and set TOPMOST so it appears above maximized IDE
        win32gui.SetWindowPos(hwnd, win32con.HWND_TOPMOST, x, y, w, h, win32con.SWP_SHOWWINDOW)
        # Then restore to normal z-order so user can use other apps
        time.sleep(0.1)
        win32gui.SetWindowPos(hwnd, win32con.HWND_NOTOPMOST, x, y, w, h, win32con.SWP_SHOWWINDOW)
        win32gui.SetForegroundWindow(hwnd)
    except Exception as e:
        print(f"Window positioning error: {e}", flush=True)

def find_hwnd_for_pid(pid):
    matching_hwnds = []
    def enum_cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            _, wpid = win32process.GetWindowThreadProcessId(hwnd)
            if wpid == pid:
                title = win32gui.GetWindowText(hwnd)
                # Filter out invisible or helper tooltips
                rect = win32gui.GetWindowRect(hwnd)
                if (rect[2] - rect[0]) > 200 and (rect[3] - rect[1]) > 200:
                    matching_hwnds.append(hwnd)
    win32gui.EnumWindows(enum_cb, None)
    return matching_hwnds[0] if matching_hwnds else None

def find_chrome_main_hwnds():
    hwnds = {}
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if 'chrome' in p.name().lower():
                cmd = p.cmdline()
                for arg in cmd:
                    if '--remote-debugging-port=9222' in arg:
                        h = find_hwnd_for_pid(p.pid)
                        if h: hwnds[9222] = h
                    elif '--remote-debugging-port=9223' in arg:
                        h = find_hwnd_for_pid(p.pid)
                        if h: hwnds[9223] = h
        except Exception:
            pass
    return hwnds

def main():
    print("=" * 65)
    print("  FORCING CHROME TABS TO FRONT (TILED SIDE-BY-SIDE)")
    print("=" * 65)

    kill_debug_chromes()

    os.makedirs(PROFILE_A, exist_ok=True)
    os.makedirs(PROFILE_B, exist_ok=True)

    scr_w, scr_h = get_screen_resolution()
    # Taskbar height approx 40px
    avail_h = scr_h - 45
    half_w = scr_w // 2

    print(f"Screen resolution: {scr_w}x{scr_h}. Tiling windows to {half_w}x{avail_h} each.")

    # Launch Chrome 1 (Port 9222) - Left Half
    print(f"\n[1/2] Launching Chrome 1 on Port {PORT_A} (Left side of screen)...")
    p1 = subprocess.Popen([
        CHROME_EXE,
        f"--remote-debugging-port={PORT_A}",
        f"--user-data-dir={PROFILE_A}",
        f"--window-position=0,0",
        f"--window-size={half_w},{avail_h}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        LOGIN_URL
    ])

    time.sleep(2)

    # Launch Chrome 2 (Port 9223) - Right Half
    print(f"[2/2] Launching Chrome 2 on Port {PORT_B} (Right side of screen)...")
    p2 = subprocess.Popen([
        CHROME_EXE,
        f"--remote-debugging-port={PORT_B}",
        f"--user-data-dir={PROFILE_B}",
        f"--window-position={half_w},0",
        f"--window-size={half_w},{avail_h}",
        "--no-first-run",
        "--no-default-browser-check",
        "--new-window",
        LOGIN_URL
    ])

    # Wait and snap windows to foreground
    print("\nWaiting for browser windows to render...")
    for _ in range(12):
        time.sleep(1)
        hwnds = find_chrome_main_hwnds()
        if 9222 in hwnds and 9223 in hwnds:
            print("[OK] Both window handles found!")
            force_window_to_front(hwnds[9222], 0, 0, half_w, avail_h)
            force_window_to_front(hwnds[9223], half_w, 0, half_w, avail_h)
            break
        elif 9222 in hwnds:
            force_window_to_front(hwnds[9222], 0, 0, half_w, avail_h)

    print("\n" + "=" * 65)
    print("  BOTH CHROME WINDOWS ARE NOW PROMINENTLY OPEN ON YOUR SCREEN!")
    print(f"  - Left Window:  Chrome 1 (Port {PORT_A})")
    print(f"  - Right Window: Chrome 2 (Port {PORT_B})")
    print("  Please log into your Upwork account in both windows.")
    print("=" * 65 + "\n")

    # Monitor loop
    while True:
        try:
            stat_a = "Waiting"
            stat_b = "Waiting"
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT_A}/json", timeout=1) as r:
                    pages = json.loads(r.read().decode())
                    for p in pages:
                        if p.get("type") == "page":
                            u = p.get("url", "").lower()
                            t = p.get("title", "")
                            if "/nx/search" in u or "/nx/find-work" in u:
                                stat_a = "LOGGED IN - READY"
                            else:
                                stat_a = f"{t[:30]}"
                            break
            except Exception:
                stat_a = "Offline"

            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{PORT_B}/json", timeout=1) as r:
                    pages = json.loads(r.read().decode())
                    for p in pages:
                        if p.get("type") == "page":
                            u = p.get("url", "").lower()
                            t = p.get("title", "")
                            if "/nx/search" in u or "/nx/find-work" in u:
                                stat_b = "LOGGED IN - READY"
                            else:
                                stat_b = f"{t[:30]}"
                            break
            except Exception:
                stat_b = "Offline"

            print(f"[LIVE STATUS] Chrome 1 (Port 9222): [{stat_a}] | Chrome 2 (Port 9223): [{stat_b}]", flush=True)

            if "READY" in stat_a and "READY" in stat_b:
                print("\n*** BOTH PORTS ARE LOGGED IN! Ready for 1-week scraper! ***", flush=True)

        except Exception as e:
            pass

        time.sleep(4)

if __name__ == "__main__":
    main()
