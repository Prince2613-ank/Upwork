"""Windows development browsers. Linux deployment uses the virtual desktops."""
import os
import signal
import subprocess
import time
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy import select, update

from server.browser import cdp_websocket
from server.db import control
from server.pipeline import setup
from server.windows_background import set_browser_visibility


def executable(wid):
    candidates = ([Path(os.environ.get("PROGRAMFILES", "C:/Program Files")) / "Google/Chrome/Application/chrome.exe",
                   Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"] if wid == "A" else
                  [Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"), Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe")])
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        return pw.chromium.executable_path


def close_browser(process, endpoint):
    if process.poll() is not None:
        return
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(cdp_websocket(endpoint), timeout=5000)
            browser.new_browser_cdp_session().send("Browser.close")
    except Exception:
        pass
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        # Terminate only this application's owned process tree, never all Chrome processes.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_leftovers(profile):
    """A hard stop of the launcher skips cleanup; close only browsers that use this app's own profile folder."""
    script = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -and $_.CommandLine.Contains($env:FLODATA_PROFILE_ARG) } "
              "| ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }")
    env = dict(os.environ, FLODATA_PROFILE_ARG=f"--user-data-dir={profile.resolve()}")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], env=env,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    time.sleep(1)


def main():
    if os.name != "nt":
        raise SystemExit("Use Docker browser services on Linux")
    settings, db = setup()
    with db.engine.begin() as c:
        options=db.settings(c)
        options['browser_windows_visible']=False
        c.execute(update(control).where(control.c.id==1).values(settings=options))
    endpoints = {"A":settings.browser_a, "B":settings.browser_b}
    if any(urlsplit(url).hostname not in ("localhost", "127.0.0.1") for url in endpoints.values()):
        raise SystemExit("Local browser service requires localhost CDP endpoints")
    processes = {}
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
    try:
        while True:
            with db.engine.connect() as c:
                # Keep the normal saved browser session; background mode changes only its window visibility.
                row=c.execute(select(control)).mappings().one()
                visible = bool(row['remote_control'] or row['settings'].get('browser_windows_visible',False))
            for wid, endpoint in endpoints.items():
                process = processes.get(wid)
                if process is not None and process.poll() is None:
                    set_browser_visibility(process.pid,visible)
                    continue
                if process is not None:
                    close_browser(process, endpoint)
                else:
                    stop_leftovers(settings.data_dir / "browsers" / wid.lower())
                    try:
                        cdp_websocket(endpoint)
                    except Exception:
                        pass
                    else:
                        raise RuntimeError(f"Port for worker {wid} is already used by another browser. Close the old scraper's dedicated browser or configure a free port.")
                profile = settings.data_dir / "browsers" / wid.lower()
                profile.mkdir(parents=True, exist_ok=True)
                args = [executable(wid),f"--remote-debugging-port={urlsplit(endpoint).port}",f"--user-data-dir={profile.resolve()}",
                        "--no-first-run","--no-default-browser-check"]
                args.append("https://www.upwork.com/nx/find-work/" if visible else "about:blank")
                startup=subprocess.STARTUPINFO()
                startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW
                startup.wShowWindow=4 if visible else 0
                processes[wid] = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                                  startupinfo=startup)
                set_browser_visibility(processes[wid].pid,visible)
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        for wid, process in processes.items():
            close_browser(process, endpoints[wid])
        db.engine.dispose()


if __name__ == "__main__":
    main()
