import json
import sys
from pathlib import Path

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def get_last_n_jobs(feed_path, n=4):
    p = Path(feed_path)
    if not p.exists():
        return []
    lines = []
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        lines = [line.strip() for line in f if line.strip()]
    jobs = []
    for l in lines[-n:]:
        try:
            jobs.append(json.loads(l))
        except:
            pass
    return jobs

print("=== SCRAPER 1 LIVE PROGRESS (PORT 9222 - ODD DAYS: DAY 3) ===")
s1_jobs = get_last_n_jobs("output/logs/live_feed_9222.jsonl", 3)
for idx, j in enumerate(s1_jobs, 1):
    job_info = j.get("job", {})
    client_info = j.get("client", {})
    revs = j.get("client_recent_history", [])
    desc_snip = (job_info.get("description") or "")[:150].replace("\n", " ")
    print(f"[{idx}] {j.get('job_title')}")
    print(f"    Target Day: Day 3 Ago | Posted: {j.get('posted_at') or j.get('posted_raw')}")
    print(f"    Client Location: {j.get('client_location')}")
    print(f"    Client Stats: {client_info.get('total_spent', 'N/A')} | {client_info.get('rating', 'N/A')} Stars ({client_info.get('jobs_posted', '0')} jobs posted)")
    print(f"    Budget / Type: {job_info.get('budget', 'N/A')} ({job_info.get('job_type', 'N/A')})")
    print(f"    Reviews Extracted: {len(revs)} un-truncated reviews")
    print(f"    Description: \"{desc_snip}...\"")
    print(f"    URL: {j.get('job_url')}")
    print()

print("=== SCRAPER 2 LIVE PROGRESS (PORT 9223 - EVEN DAYS: DAY 2) ===")
s2_jobs = get_last_n_jobs("output/logs/live_feed_9223.jsonl", 3)
for idx, j in enumerate(s2_jobs, 1):
    job_info = j.get("job", {})
    client_info = j.get("client", {})
    revs = j.get("client_recent_history", [])
    desc_snip = (job_info.get("description") or "")[:150].replace("\n", " ")
    print(f"[{idx}] {j.get('job_title')}")
    print(f"    Target Day: Day 2 Ago | Posted: {j.get('posted_at') or j.get('posted_raw')}")
    print(f"    Client Location: {j.get('client_location')}")
    print(f"    Client Stats: {client_info.get('total_spent', 'N/A')} | {client_info.get('rating', 'N/A')} Stars ({client_info.get('jobs_posted', '0')} jobs posted)")
    print(f"    Budget / Type: {job_info.get('budget', 'N/A')} ({job_info.get('job_type', 'N/A')})")
    print(f"    Reviews Extracted: {len(revs)} un-truncated reviews")
    print(f"    Description: \"{desc_snip}...\"")
    print(f"    URL: {j.get('job_url')}")
    print()
