import sqlite3
import json
import sys
from collections import Counter
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8')

dbs = {
    "Combined Weekend DB": "output/database_today.db",
    "Weekend Partition DB": "output/database_weekend_2026-10-17_to_2026-10-18.db",
    "Sunday Only DB": "output/database_daily_2026-10-18.db",
    "Saturday Only DB": "output/database_daily_2026-10-17.db",
    "Yesterday Alias DB": "output/database_yesterday.db"
}

for name, path in dbs.items():
    try:
        conn = sqlite3.connect(path)
        rows = conn.execute("SELECT job_json, saved_at FROM jobs").fetchall()
        conn.close()
        
        date_counts = Counter()
        has_reviews = 0
        zero_reviews = 0
        earliest_dt = "9999"
        latest_dt = "0000"
        countries = Counter()
        
        for r, sat in rows:
            d = json.loads(r)
            p_iso = d.get("posted_at") or ""
            dt = p_iso[:10] if len(p_iso) >= 10 else "Unknown"
            date_counts[dt] += 1
            if p_iso:
                if p_iso < earliest_dt: earliest_dt = p_iso
                if p_iso > latest_dt: latest_dt = p_iso
                
            revs = d.get("client_recent_history") or []
            if revs: has_reviews += 1
            else: zero_reviews += 1
            
            loc = (d.get("client_location") or (d.get("client") or {}).get("location") or "Unknown")
            countries[loc] += 1

        print(f"\n========================================================")
        print(f"DATABASE: {name} ({path})")
        print(f"Total Rows: {len(rows):,}")
        print(f"Date Breakdown:")
        for dt, cnt in sorted(date_counts.items(), reverse=True):
            print(f"   • {dt}: {cnt:,} jobs")
        print(f"Earliest Job: {earliest_dt}")
        print(f"Latest Job:   {latest_dt}")
        print(f"Review Breakdown: {has_reviews:,} with reviews | {zero_reviews:,} 0-reviews")
        print(f"Unique Locations: {len(countries):,}")
    except Exception as e:
        print(f"Error {name}: {e}")
