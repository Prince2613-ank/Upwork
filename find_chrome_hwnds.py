import win32gui
import win32process
import psutil

chrome_pids = set()
for p in psutil.process_iter(['pid', 'name', 'cmdline']):
    if 'chrome' in p.name().lower():
        chrome_pids.add(p.pid)
        cmd = p.cmdline()
        if any('remote-debugging' in arg for arg in cmd):
            print(f"Debug Chrome PID: {p.pid}, Port: {[a for a in cmd if 'remote-debugging' in a]}")

def enum_cb(hwnd, _):
    tid, pid = win32process.GetWindowThreadProcessId(hwnd)
    if pid in chrome_pids:
        title = win32gui.GetWindowText(hwnd)
        rect = win32gui.GetWindowRect(hwnd)
        vis = win32gui.IsWindowVisible(hwnd)
        print(f"HWND {hwnd} | PID {pid} | Vis: {vis} | Rect: {rect} | Title: {title}")

win32gui.EnumWindows(enum_cb, None)
