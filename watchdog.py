"""
Watchdog: Auto-monitors the Upwork collector every 2 minutes.
- Detects Cloudflare stops, stuck states, crashes
- Auto-resumes via /api/resume
- Resets bad checkpoint status fields
- Logs all actions with timestamps
"""

import json
import time
import requests
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

CHECKPOINT_PATH = Path("output/checkpoint.json")
DASHBOARD_URL = "http://127.0.0.1:8000"
CHECK_INTERVAL = 120          # seconds between checks
STUCK_THRESHOLD = 300         # seconds with no new jobs = stuck
MAX_RESUME_ATTEMPTS = 5       # before giving up and restarting server

log_path = Path("output/watchdog.log")

def log(msg: str, level: str = "INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    with open(log_path, "a", encoding="utf-8", errors="replace") as f:
        f.write(line + "\n")

def read_checkpoint():
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Failed to read checkpoint: {e}", "ERROR")
        return None

def write_checkpoint_status(status: str):
    try:
        d = read_checkpoint()
        if d:
            d["status"] = status
            CHECKPOINT_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")
            log(f"Checkpoint status reset to '{status}'")
    except Exception as e:
        log(f"Failed to write checkpoint: {e}", "ERROR")

def get_api_status():
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/status", timeout=5)
        return r.json()
    except Exception:
        return None

def call_resume():
    try:
        r = requests.post(f"{DASHBOARD_URL}/api/resume", timeout=5)
        return r.json()
    except Exception as e:
        log(f"Resume call failed: {e}", "ERROR")
        return None

def is_dashboard_alive():
    try:
        r = requests.get(f"{DASHBOARD_URL}/api/status", timeout=5)
        return r.status_code == 200
    except Exception:
        return False

def restart_dashboard():
    log("Restarting dashboard server...", "WARN")
    try:
        subprocess.Popen(
            [sys.executable, "main.py", "--dashboard"],
            cwd=str(Path(__file__).parent),
            creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        )
        time.sleep(6)
        if is_dashboard_alive():
            log("Dashboard restarted successfully.", "INFO")
            return True
        else:
            log("Dashboard restart failed — may need manual intervention.", "ERROR")
            return False
    except Exception as e:
        log(f"Dashboard restart error: {e}", "ERROR")
        return False

def main():
    log("=" * 55)
    log("  WATCHDOG STARTED — checking every 2 minutes")
    log("=" * 55)

    last_job_count = 0
    last_job_time = time.time()
    resume_attempts = 0

    while True:
        try:
            log("--- Watchdog check ---")

            # 1. Check dashboard alive
            if not is_dashboard_alive():
                log("Dashboard is DOWN!", "ERROR")
                restarted = restart_dashboard()
                if restarted:
                    time.sleep(5)
                    call_resume()
                    log("Resume sent after restart.", "INFO")
                time.sleep(CHECK_INTERVAL)
                continue

            # 2. Get API status
            api = get_api_status()
            ckpt = read_checkpoint()

            if not api or not ckpt:
                log("Could not get status — skipping this cycle.", "WARN")
                time.sleep(CHECK_INTERVAL)
                continue

            status = api.get("status", "unknown")
            jobs_processed = api.get("jobs_processed", 0)
            current_page = api.get("current_page", 0)
            ckpt_jobs = len(ckpt.get("processed_job_ids", []))
            ckpt_status = ckpt.get("status", "unknown")

            log(f"Status={status} | API_Jobs={jobs_processed} | Checkpoint_Jobs={ckpt_jobs} | Page={current_page} | Ckpt_Status={ckpt_status}")

            # 3. Detect new jobs
            current_count = max(jobs_processed, ckpt_jobs)
            if current_count > last_job_count:
                log(f"Progress detected: {last_job_count} -> {current_count} jobs [OK]")
                last_job_count = current_count
                last_job_time = time.time()
                resume_attempts = 0

            # 4. Check for STUCK / STOPPED states
            time_since_progress = time.time() - last_job_time
            needs_resume = False
            reason = ""

            if status in ("stopped_security_prompt", "stopped", "error"):
                needs_resume = True
                reason = f"Status is '{status}'"

            elif ckpt_status in ("stopped_security_prompt", "stopped"):
                needs_resume = True
                reason = f"Checkpoint status is '{ckpt_status}'"

            elif status == "running" and time_since_progress > STUCK_THRESHOLD:
                needs_resume = True
                reason = f"No progress for {int(time_since_progress)}s (stuck)"

            # 5. Auto-fix
            if needs_resume:
                if resume_attempts >= MAX_RESUME_ATTEMPTS:
                    log(f"Max resume attempts ({MAX_RESUME_ATTEMPTS}) reached. Restarting dashboard.", "ERROR")
                    restart_dashboard()
                    resume_attempts = 0
                    time.sleep(5)

                log(f"AUTO-FIX triggered: {reason}", "WARN")
                write_checkpoint_status("running")
                result = call_resume()
                log(f"Resume response: {result}", "INFO")
                resume_attempts += 1
                last_job_time = time.time()  # reset stuck timer

            elif status == "completed":
                log("Collection COMPLETED! All pages done. Watchdog exiting.", "INFO")
                break

            else:
                log(f"All good — collector running normally ({current_count} jobs so far).")

        except Exception as e:
            log(f"Watchdog loop error: {e}", "ERROR")

        time.sleep(CHECK_INTERVAL)

    log("Watchdog finished.")

if __name__ == "__main__":
    main()
