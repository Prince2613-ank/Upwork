import sqlite3
import json
from collections import defaultdict
from pathlib import Path

DB_PATH = Path("output/database_yesterday.db")
conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

total = len(rows)
dates = defaultdict(int)
hours = defaultdict(int)
locs = defaultdict(int)
timestamps = []

for jid, raw_j in rows:
    try:
        d = json.loads(raw_j)
        p = d.get("posted_at", "")
        cloc = d.get("client", {}).get("location", "") or "Unknown"
        if p:
            dt = p[:10]
            dates[dt] += 1
            if dt == "2026-10-16":
                hr = p[11:13]
                hours[hr] += 1
                timestamps.append(p)
                locs[cloc] += 1
    except Exception:
        pass

timestamps.sort()

print("=" * 70)
print(f"AUDIT REPORT: YESTERDAY JOBS COMPLETENESS (2026-10-16)")
print("=" * 70)
print(f"Total Database Rows: {total}")
print(f"Dates Distribution: {dict(dates)}")
print(f"\n24-Hour Coverage Window for 2026-10-16:")
if timestamps:
    print(f"  Oldest Job Posted At: {timestamps[0]} (Boundary start)")
    print(f"  Newest Job Posted At: {timestamps[-1]} (Boundary end)")
print(f"\nHourly Job Distribution (00:00 - 23:00 UTC):")
for h in range(24):
    h_str = f"{h:02d}"
    cnt = hours.get(h_str, 0)
    bar = "#" * (cnt // 5)
    print(f"  Hour {h_str}:00 UTC: {cnt:3d} jobs | {bar}")

print(f"\nTop 15 Client Countries in Yesterday's Dataset:")
sorted_locs = sorted(locs.items(), key=lambda x: x[1], reverse=True)
for loc, cnt in sorted_locs[:15]:
    print(f"  {loc:30s}: {cnt:4d} jobs")
print(f"Total Unique Client Locations: {len(locs)}")
print("=" * 70)
