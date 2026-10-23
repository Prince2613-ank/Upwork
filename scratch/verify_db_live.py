import sqlite3
import json
import time
from pathlib import Path
from datetime import datetime

base_dir = Path("output")
db_1week = base_dir / "database_1week.db"
db_14days = base_dir / "database_14days.db"
db_main = base_dir / "database.db"

print("=" * 60)
print("FLODATA UPWORK INTELLIGENCE - LIVE DATABASE INTEGRITY AUDIT")
print(f"Audit executed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("Mode: Strictly Read-Only (Non-blocking, scraper uninterrupted)")
print("=" * 60)

for name, db_path in [("database_1week.db", db_1week), ("database_14days.db", db_14days), ("database.db", db_main)]:
    if not db_path.exists():
        print(f"[-] {name} does not exist.")
        continue
    
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    try:
        conn = sqlite3.connect(uri, uri=True, timeout=5)
        cur = conn.cursor()
        
        # Check table columns
        cur.execute("PRAGMA table_info(jobs)")
        cols = [r[1] for r in cur.fetchall()]
        
        # Check row count
        cur.execute("SELECT COUNT(*) FROM jobs")
        total_count = cur.fetchone()[0]
        
        # Check sample recent entries
        if "saved_at" in cols:
            cur.execute("SELECT job_id, saved_at, job_json, (raw_html IS NOT NULL AND length(raw_html) > 0) FROM jobs ORDER BY rowid DESC LIMIT 5")
        else:
            cur.execute("SELECT job_id, 'N/A', job_json, 0 FROM jobs ORDER BY rowid DESC LIMIT 5")
            
        recent = cur.fetchall()
        
        print(f"\n[+] Database: {name}")
        print(f"    File Size: {db_path.stat().st_size / (1024*1024):.2f} MB")
        print(f"    Table 'jobs' columns: {', '.join(cols)}")
        print(f"    Total Records: {total_count:,}")
        
        print("    Recent 5 Records (by insertion order):")
        for jid, saved_at, raw_json, has_html in recent:
            try:
                data = json.loads(raw_json) if raw_json else {}
                title = data.get("job_title", "N/A")
                loc = data.get("client_location") or (data.get("client") or {}).get("location") or "N/A"
                posted = data.get("posted_raw") or data.get("posted_at") or "N/A"
                hist_cnt = len(data.get("client_recent_history") or [])
                budget = data.get("budget") or data.get("hourly_rate") or data.get("budget_snippet") or "N/A"
                print(f"      - ID: {jid} | Saved At: {saved_at} | Has HTML: {bool(has_html)}")
                print(f"        Title: {title[:45]} | Loc: {loc} | Budget: {budget}")
                print(f"        Posted: {posted} | Reviews Captured: {hist_cnt}")
            except Exception as e:
                print(f"      - ID: {jid} (Parse Error: {e})")
                
        conn.close()
    except Exception as e:
        print(f"[-] Error reading {name}: {e}")

print("\n" + "=" * 60)
