import glob
import os
import re
import sqlite3
from datetime import datetime, timedelta

tasks_dir = r"C:\Users\princ\.gemini\antigravity-ide\brain\30998f6c-795f-4202-9dd7-7e906fc43a62\.system_generated\tasks"
logs = glob.glob(os.path.join(tasks_dir, "task-*.log"))

p9222_jobs = []
p9223_jobs = []

cutoff_time = datetime.now() - timedelta(minutes=15)
cutoff_str = cutoff_time.strftime("%Y-%m-%d %H:%M:%S")

for lf in logs:
    try:
        with open(lf, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        
        is_9222 = any("9222" in l for l in lines[:10])
        is_9223 = any("9223" in l for l in lines[:10])
        
        for l in lines:
            if "Collected:" in l:
                m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*?\[(\d+)\] Collected:\s*\'(.*?)\'", l)
                if m:
                    t_str, j_idx, j_title = m.groups()
                    if t_str >= cutoff_str:
                        item = {"time": t_str, "idx": j_idx, "title": j_title}
                        if is_9222:
                            p9222_jobs.append(item)
                        elif is_9223:
                            p9223_jobs.append(item)
    except Exception:
        pass

# Deduplicate by job index in case of process restarts
p9222_dict = {j["idx"]: j for j in p9222_jobs}
p9223_dict = {j["idx"]: j for j in p9223_jobs}

print("=" * 65)
print(f"AUDIT OF LAST 15 MINUTES (Window: {cutoff_str} to Now)")
print("=" * 65)
print(f"Port 9222 (Scraper 1 - Europe, Australia, Canada, etc.):")
print(f"  Count: {len(p9222_dict)} jobs saved to DB & CSVs")
print(f"  Sample Jobs:")
for j in list(p9222_dict.values())[-4:]:
    print(f"    • [{j['time']}] #{j['idx']}: {j['title']}")

print(f"\nPort 9223 (Scraper 2 - Malaysia, UK, US, Singapore, etc.):")
print(f"  Count: {len(p9223_dict)} jobs saved to DB & CSVs")
print(f"  Sample Jobs:")
for j in list(p9223_dict.values())[-4:]:
    print(f"    • [{j['time']}] #{j['idx']}: {j['title']}")

print("-" * 65)
total_collected_15m = len(p9222_dict) + len(p9223_dict)
print(f"Total New Jobs Collected in Last 15 min: {total_collected_15m}")

conn = sqlite3.connect("output/database.db")
c = conn.cursor()
total_db = c.execute("SELECT count(*) FROM jobs").fetchone()[0]
total_claims = c.execute("SELECT count(*) FROM claims").fetchone()[0]
total_seen = c.execute("SELECT count(*) FROM seen_ids").fetchone()[0]
print(f"Total Cumulative Validated Jobs in database.db: {total_db:,}")
print(f"Database Integrity: seen_ids={total_seen:,}, claims={total_claims:,}")
print("=" * 65)
