import ctypes

user32 = ctypes.windll.user32
titles = []

def enum_proc(hwnd, lparam):
    length = user32.GetWindowTextLengthW(hwnd)
    if length > 0 and user32.IsWindowVisible(hwnd):
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        titles.append((hwnd, buf.value))
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows(WNDENUMPROC(enum_proc), 0)

print("Visible Windows:")
for hwnd, t in titles:
    t_lower = t.lower()
    if any(k in t_lower for k in ['chrome', 'edge', 'upwork', 'hub', 'flodata', 'antigravity', 'port']):
        print(f"HWND {hwnd}: {t}")
