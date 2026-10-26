"""Private virtual desktop. Chromium restarts retain the per-container profile."""
import os
import signal
import subprocess
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from playwright.sync_api import sync_playwright

children = []


def launch(args):
    child = subprocess.Popen(args)
    children.append(child)
    return child


def shutdown(*_):
    for child in children:
        if child.poll() is None:
            child.terminate()
    raise SystemExit(0)


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)
os.makedirs("/data/profile", exist_ok=True)
launch(["Xvfb", ":99", "-screen", "0", "1440x1000x24", "-nolisten", "tcp"])
time.sleep(1)
launch(["x11vnc", "-display", ":99", "-localhost", "-forever", "-shared", "-nopw", "-rfbport", "5900"])
remote = subprocess.Popen(["websockify", "--web=/usr/share/novnc", "6080", "localhost:5900"], start_new_session=True)
children.append(remote)
remote_lock = threading.Lock()


class RemoteControl(BaseHTTPRequestHandler):
    def do_POST(self):
        global remote
        if self.path != "/disconnect":
            self.send_error(404)
            return
        with remote_lock:
            os.killpg(remote.pid, signal.SIGTERM)
            remote.wait(timeout=5)
            children.remove(remote)
            remote = subprocess.Popen(["websockify", "--web=/usr/share/novnc", "6080", "localhost:5900"], start_new_session=True)
            children.append(remote)
        self.send_response(200)
        self.end_headers()


threading.Thread(target=HTTPServer(("0.0.0.0", 7070), RemoteControl).serve_forever, daemon=True).start()
launch(["socat", "TCP-LISTEN:9222,fork,reuseaddr", "TCP:127.0.0.1:9224"])
with sync_playwright() as pw:
    executable = pw.chromium.executable_path
while True:
    browser = launch([executable, "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=9224",
        "--user-data-dir=/data/profile", "--no-first-run", "--no-default-browser-check",
        "--disable-dev-shm-usage", "--window-size=1440,1000", os.getenv("BROWSER_START_URL", "https://www.upwork.com/nx/find-work/")])
    while browser.poll() is None:
        with remote_lock:
            if any(p is not browser and p.poll() is not None for p in children):
                shutdown()
        time.sleep(2)
    children.remove(browser)
    time.sleep(3)
