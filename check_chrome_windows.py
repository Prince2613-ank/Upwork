import ctypes

user32 = ctypes.windll.user32

def enum_proc(hwnd, lparam):
    buf_class = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf_class, 256)
    if "Chrome_WidgetWin_1" in buf_class.value:
        length = user32.GetWindowTextLengthW(hwnd)
        buf_title = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf_title, length + 1)
        print(f"HWND {hwnd} | Class: {buf_class.value} | Title: {buf_title.value}")
    return True

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
user32.EnumWindows(WNDENUMPROC(enum_proc), 0)
