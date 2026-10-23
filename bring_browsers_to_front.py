import ctypes
import json
import urllib.request

user32 = ctypes.windll.user32

def get_pids():
    pids = []
    for port in [9222, 9223]:
        try:
            with urllib.request.urlopen(f"http://localhost:{port}/json/version", timeout=1) as res:
                # Port is active
                pass
        except Exception:
            continue
    return pids

def bring_window_to_front():
    # Enumerate all windows and restore/bring to front any chrome/edge windows that have 9222/9223 or Upwork in title
    def enum_windows_callback(hwnd, lparam):
        if user32.IsWindow(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                if "upwork" in title or "chrome" in title or "edge" in title:
                    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                    user32.SetForegroundWindow(hwnd)
                    user32.BringWindowToTop(hwnd)
                    print(f"Brought window to front: {buf.value}")
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows(WNDENUMPROC(enum_windows_callback), 0)

if __name__ == "__main__":
    bring_window_to_front()
