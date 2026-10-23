import os
import sys
import time
import json
import urllib.request
import subprocess

PORT_A = 9222
PORT_B = 9223

def is_port_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False

def get_page_status(port: int):
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=1.5) as r:
            pages = json.loads(r.read().decode())
            for p in pages:
                if p.get("type") == "page":
                    return p.get("title", ""), p.get("url", "")
            return "Online", ""
    except Exception:
        return "Offline", ""

def main():
    print("=" * 65)
    print("  SCRAPER SUPERVISOR: LISTENING FOR PORTS 9222 & 9223")
    print("  Waiting for open_live_tabs.bat to be launched...")
    print("=" * 65)

    last_report = 0

    while True:
        s1 = is_port_ready(PORT_A)
        s2 = is_port_ready(PORT_B)

        now = time.time()
        if now - last_report >= 5:
            last_report = now
            t1, u1 = get_page_status(PORT_A)
            t2, u2 = get_page_status(PORT_B)
            print(f"[PORT CHECK] Port 9222: {'ONLINE' if s1 else 'WAITING'} ({t1[:30]}) | Port 9223: {'ONLINE' if s2 else 'WAITING'} ({t2[:30]})", flush=True)

        if s1 and s2:
            print("\n*** BOTH PORTS (9222 & 9223) ARE CONNECTED! ***\n", flush=True)
            # Give 2 seconds for pages to settle
            time.sleep(2)
            # Launch run_dual_week_scrapers.py
            print("Launching 1-Week Scraper Orchestrator on both live tabs...", flush=True)
            subprocess.run([sys.executable, "run_dual_week_scrapers.py"])
            break

        time.sleep(1)

if __name__ == "__main__":
    main()
