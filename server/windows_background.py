"""Show or hide only the main windows owned by a dedicated scraper browser PID."""
import os


def set_browser_visibility(process_id, visible):
    if os.name != 'nt':
        return []
    import ctypes
    from ctypes import wintypes

    user32=ctypes.WinDLL('user32', use_last_error=True)
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    user32.EnumWindows.argtypes=[callback_type,wintypes.LPARAM]
    user32.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user32.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
    user32.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
    user32.IsWindowVisible.argtypes=[wintypes.HWND]
    changed=[]

    @callback_type
    def visit(hwnd,_):
        owner=wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd,ctypes.byref(owner))
        if owner.value==process_id:
            name=ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd,name,len(name))
            if name.value=='Chrome_WidgetWin_1':
                before=bool(user32.IsWindowVisible(hwnd))
                if before!=visible:
                    user32.ShowWindow(hwnd,4 if visible else 0)  # Show without activating, or hide.
                changed.append({'handle':int(hwnd),'was_visible':before,'visible':bool(user32.IsWindowVisible(hwnd))})
        return True

    user32.EnumWindows(visit,0)
    return changed


def main():
    """Attach visibility management to an already-running local browser supervisor."""
    import argparse
    import ctypes
    import time
    from ctypes import wintypes
    from urllib.parse import urlsplit
    from playwright.sync_api import sync_playwright
    from sqlalchemy import select
    from server.config import Settings
    from server.db import Database, control
    from server.browser import cdp_websocket

    parser=argparse.ArgumentParser()
    parser.add_argument('--parent-pid',type=int,required=True)
    args=parser.parse_args()
    if os.name!='nt':
        raise SystemExit('Local window visibility is Windows-only')
    settings=Settings()
    endpoints=[settings.browser_a,settings.browser_b]
    if any(urlsplit(url).hostname not in ('localhost','127.0.0.1') for url in endpoints):
        raise SystemExit('Only local dedicated browser endpoints are supported')
    kernel=ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
    kernel.OpenProcess.restype=wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes=[wintypes.HANDLE,wintypes.DWORD]
    kernel.CloseHandle.argtypes=[wintypes.HANDLE]
    parent=kernel.OpenProcess(0x00100000,False,args.parent_pid)
    if not parent:
        raise SystemExit('Browser supervisor is not available')
    db=Database(settings.database_url)
    connections={}
    try:
        with sync_playwright() as pw:
            while kernel.WaitForSingleObject(parent,0)==258:  # WAIT_TIMEOUT: parent is still running.
                with db.engine.connect() as c:
                    row=c.execute(select(control)).mappings().one()
                    visible=bool(row['remote_control'] or row['settings'].get('browser_windows_visible',False))
                for endpoint in endpoints:
                    try:
                        connection=connections.get(endpoint)
                        if connection is None or not connection[0].is_connected():
                            browser=pw.chromium.connect_over_cdp(cdp_websocket(endpoint),timeout=5000)
                            session=browser.new_browser_cdp_session()
                            processes=session.send('SystemInfo.getProcessInfo')['processInfo']
                            session.detach()
                            pid=int(next(p['id'] for p in processes if p['type']=='browser'))
                            connection=(browser,pid)
                            connections[endpoint]=connection
                        set_browser_visibility(connection[1],visible)
                    except Exception:
                        # The owning supervisor recovers crashed browsers; reconnect on the next pass.
                        connections.pop(endpoint,None)
                time.sleep(1)
    finally:
        db.engine.dispose()
        kernel.CloseHandle(parent)


if __name__=='__main__':
    main()
