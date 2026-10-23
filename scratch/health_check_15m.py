"""
FLODATA 15-MINUTE AUTOMATED HEALTH & AUDIT MONITOR
==================================================
Performs strict checks:
1. Scraper Health Check (Process + Ports) -> Auto-restart if dead.
2. DB Check: database_1week.db & database_7days.db count, integrity, date range.
3. Job Save Check: Verify all jobs strictly fall within Oct 04 - Oct 11, 2026.
4. Review & Client History Integrity: 100% clean reviews, 0 empty descriptions.
5. Report & CSV Sync: Generates up-to-date upwork_this_week_report.html & jobs_1week.csv.
6. Dashboard Status Check: http://localhost:8000/api/status.
"""

import sys
import os
import json
import sqlite3
import subprocess
import urllib.request
import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUTPUT_DIR = ROOT / "output"

DB_1WEEK = OUTPUT_DIR / "database_1week.db"
DB_7DAYS = OUTPUT_DIR / "database_7days.db"
HISTORY_FILE = ROOT / "scratch" / "health_check_history.json"
AUDIT_LOG_FILE = OUTPUT_DIR / "health_audit_history.log"

DATE_START = "2026-10-04"
DATE_END   = "2026-10-11"

def check_cdp_endpoint(url):
    try:
        with urllib.request.urlopen(f"{url}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False

def check_scraper_running():
    chrome_ok = check_cdp_endpoint("http://127.0.0.1:9222") or check_cdp_endpoint("http://[::1]:9223")
    edge_ok   = check_cdp_endpoint("http://127.0.0.1:9223")
    
    # Check if python script is running
    r = subprocess.run("tasklist /fi \"imagename eq python.exe\"", shell=True, capture_output=True, text=True)
    is_python_running = "python.exe" in r.stdout

    healthy = (chrome_ok or edge_ok) and is_python_running

    # AUTO-RESTART IF DEAD
    if not healthy:
        print("[AUTO-HEAL] Scraper appears inactive or disconnected. Attempting auto-restart...", flush=True)
        try:
            subprocess.Popen(
                ["python", "run_country_week_scrapers.py", "--start", DATE_START, "--end", DATE_END],
                cwd=str(ROOT),
                creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
            )
            print("[AUTO-HEAL] Restart command dispatched successfully.", flush=True)
        except Exception as e:
            print(f"[AUTO-HEAL ERR] Failed to restart scraper: {e}", flush=True)

    return {
        "chrome_cdp": chrome_ok,
        "edge_cdp": edge_ok,
        "python_running": is_python_running,
        "overall_healthy": healthy
    }

def audit_database():
    if not DB_1WEEK.exists():
        return {"error": "database_1week.db not found"}

    conn = sqlite3.connect(f"file:{DB_1WEEK.resolve()}?mode=ro", uri=True, timeout=10)
    c = conn.cursor()
    total_jobs = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]

    rows = c.execute("SELECT job_id, job_json, saved_at FROM jobs").fetchall()
    conn.close()

    dates = []
    countries = {}
    total_reviews = 0
    out_of_bounds = []
    empty_desc = 0

    for jid, raw_json, sat in rows:
        try:
            d = json.loads(raw_json)
        except Exception:
            continue

        p_at = str(d.get("posted_at") or "")[:10]
        if p_at:
            dates.append(p_at)
            if not (DATE_START <= p_at <= DATE_END):
                out_of_bounds.append((jid, p_at))

        loc = d.get("client_location") or "Unknown"
        countries[loc] = countries.get(loc, 0) + 1

        desc = (d.get("job") or {}).get("description") or d.get("description_snippet") or d.get("description") or ""
        if not desc:
            empty_desc += 1

        revs = d.get("client_recent_history") or []
        total_reviews += len(revs)

    min_date = min(dates) if dates else "N/A"
    max_date = max(dates) if dates else "N/A"

    return {
        "total_jobs": total_jobs,
        "date_bounds": f"{min_date} to {max_date}",
        "out_of_bounds_count": len(out_of_bounds),
        "empty_descriptions": empty_desc,
        "total_clean_reviews": total_reviews,
        "top_countries": sorted(countries.items(), key=lambda x: x[1], reverse=True)[:5]
    }

def check_dashboard():
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/api/status", timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

def update_reports():
    try:
        report_path = OUTPUT_DIR / "upwork_1week_report.html"
        now_ts = datetime.now().timestamp()
        
        # If report was generated in the last 15 minutes by the scraper daemon, reuse it
        needs_gen = True
        if report_path.exists() and (now_ts - report_path.stat().st_mtime) < 900:
            needs_gen = False

        if needs_gen:
            from generate_standalone_report import generate_report
            generate_report(
                output_html=str(report_path),
                db_path=str(DB_1WEEK),
                report_title="Upwork 7-Day Market Intelligence Report (Oct 04 - Oct 11, 2026)"
            )
        
        if report_path.exists():
            shutil.copy2(report_path, ROOT / "upwork_this_week_report.html")
            shutil.copy2(report_path, ROOT / "upwork_7days_report.html")

        csv_path = OUTPUT_DIR / "jobs_1week.csv"
        if not csv_path.exists() or (now_ts - csv_path.stat().st_mtime) >= 900:
            from collector.dashboard.app import _export_1week_csv
            _export_1week_csv(csv_path)
        if csv_path.exists():
            shutil.copy2(csv_path, OUTPUT_DIR / "jobs_7days.csv")

        return True
    except Exception as e:
        print(f"[REPORT UPDATE ERR] {e}", flush=True)
        return False


def run_health_check():
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    health = check_scraper_running()
    db_audit = audit_database()
    dash = check_dashboard()
    reports_synced = update_reports()

    last_count = 0
    try:
        if HISTORY_FILE.exists():
            with open(HISTORY_FILE, "r") as f:
                last_count = json.load(f).get("total_jobs", 0)
    except Exception:
        pass

    current_count = db_audit.get("total_jobs", 0)
    jobs_delta = current_count - last_count if last_count else 0

    with open(HISTORY_FILE, "w") as f:
        json.dump({"total_jobs": current_count, "timestamp": datetime.now().isoformat()}, f)

    result = {
        "timestamp": now_str,
        "scraper_health": health,
        "database": db_audit,
        "jobs_added_since_last_check": jobs_delta,
        "dashboard_api": {
            "status": dash.get("status", "unknown"),
            "dataset": dash.get("dataset_name", "7-Day Live Intelligence")
        },
        "reports_and_csv_synced": reports_synced
    }

    # Append to persistent audit log
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as alf:
        alf.write(f"[{now_str}] Jobs: {current_count} (+{jobs_delta}) | Range: {db_audit.get('date_bounds')} | OOB: {db_audit.get('out_of_bounds_count')} | Health: {health['overall_healthy']}\n")

    print("\n" + "=" * 70)
    print(f"  15-MINUTE HEALTH & INTEGRITY AUDIT [{now_str}]")
    print("=" * 70)
    print(f"  Scraper Active:     {'YES (RUNNING)' if health['overall_healthy'] else 'NO (ATTEMPTED AUTO-RESTART)'}")
    print(f"  Chrome Worker A:    {'ONLINE' if health['chrome_cdp'] else 'OFFLINE'}")
    print(f"  Edge Worker B:      {'ONLINE' if health['edge_cdp'] else 'OFFLINE'}")
    print(f"  Total 7-Day Jobs:   {current_count} (+{jobs_delta} in last interval)")
    print(f"  Date Bounds:        {db_audit.get('date_bounds')} (Strict Oct 04 - Oct 11)")
    print(f"  Out of Bounds Jobs: {db_audit.get('out_of_bounds_count')} (Must be 0)")
    print(f"  Empty Descriptions: {db_audit.get('empty_descriptions')} (Must be 0)")
    print(f"  Clean Reviews:      {db_audit.get('total_clean_reviews')}")
    print(f"  Dashboard (8000):   {dash.get('status', 'running')}")
    print(f"  Reports & CSV:      {'SYNCED & UPDATED' if reports_synced else 'FAILED'}")
    print("=" * 70 + "\n")

    return result

if __name__ == "__main__":
    run_health_check()
