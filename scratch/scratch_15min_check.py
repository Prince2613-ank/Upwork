import sys
import os
import sqlite3
import urllib.request
import json
from pathlib import Path

# Force utf-8 output on Windows terminal
if sys.stdout.encoding != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

# 1. Scraper Health Check via API
try:
    req = urllib.request.urlopen("http://127.0.0.1:8000/api/status", timeout=3)
    dash_status = json.loads(req.read().decode())
    print("[HEALTH] Dashboard & API online at http://localhost:8000")
    print(f"   Status: {dash_status.get('status')}")
    print(f"   Dataset: {dash_status.get('dataset_name')}")
    print(f"   Worker A: {dash_status.get('scraper_1', {}).get('status')} on Port 9222")
    print(f"   Worker B: {dash_status.get('scraper_2', {}).get('status')} on Port 9223")
except Exception as e:
    print(f"[HEALTH] Dashboard API offline: {e}")

# 2. Database & Jobs Saved Check
print("\n--- DATABASE VERIFICATION ---")
for db_name in ["database_daily_2026-10-15.db", "database_yesterday.db", "database_today.db", "database.db"]:
    p = Path("output") / db_name
    if p.exists():
        conn = sqlite3.connect(p)
        cnt = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        # Check if saved_at column exists
        cols = [col[1] for col in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        last_saved = "N/A"
        if "saved_at" in cols:
            last_saved = conn.execute("SELECT max(saved_at) FROM jobs").fetchone()[0] or "N/A"
        conn.close()
        print(f"[DB] {db_name}: {cnt:,} jobs saved (Last saved: {last_saved})")
    else:
        print(f"[DB] {db_name}: Not found")

# 3. Report Check
print("\n--- REPORT COMPILATION CHECK ---")
for rep in ["upwork_yesterday_report.html", "output/upwork_today_report.html", "output/jobs_today.csv"]:
    rp = Path(rep)
    if rp.exists():
        sz = rp.stat().st_size / 1024
        print(f"[REPORT] {rep}: {sz:.1f} KB exists and ready")
    else:
        print(f"[REPORT] {rep}: Not found yet")
