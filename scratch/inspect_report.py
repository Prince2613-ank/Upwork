import re, json, sys
from collections import Counter

sys.stdout.reconfigure(encoding='utf-8')

path = r'C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\upwork_1week_28-09-2026_to_04-10-2026.html'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    text = f.read()

m = re.search(r'const\s+JOBS\s*=\s*(\[.*?\]);', text)
if m:
    jobs = json.loads(m.group(1))
    print(f"Total jobs in JOBS: {len(jobs)}")
    
    # Extract date part (YYYY-MM-DD) from posted
    date_strs = []
    invalid_dates = []
    for j in jobs:
        p = str(j.get('posted', ''))
        if len(p) >= 10:
            date_strs.append(p[:10])
        else:
            invalid_dates.append(p)
            
    print("\nDate breakdown (YYYY-MM-DD):")
    counts = Counter(date_strs)
    for d, c in sorted(counts.items(), reverse=True):
        print(f"  {d}: {c} jobs")
    if invalid_dates:
        print(f"  Invalid / short dates: {len(invalid_dates)} -> {invalid_dates[:5]}")

    # Check date range limits
    min_date = min(date_strs) if date_strs else None
    max_date = max(date_strs) if date_strs else None
    print(f"\nMinimum date in file: {min_date}")
    print(f"Maximum date in file: {max_date}")

    # Are there any jobs outside 2026-09-28 to 2026-10-04?
    out_of_bounds = [j for j in jobs if not ('2026-09-28' <= str(j.get('posted', ''))[:10] <= '2026-10-04')]
    print(f"Jobs outside 2026-09-28 to 2026-10-04: {len(out_of_bounds)}")
    if out_of_bounds:
        for obj in out_of_bounds[:10]:
            print("  Out of bound job:", obj.get('id'), obj.get('posted'), obj.get('posted_raw'))
