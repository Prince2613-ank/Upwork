import json, re

with open('upwork_14days_fetched_report.html', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'const JOBS = (\[.*?\]);\s*let filteredJobs', text, re.DOTALL)
jobs = json.loads(m.group(1))

count = 0
for j in jobs:
    for r in j.get('reviews', []):
        fb = r.get('feedback', '')
        low = fb.lower()
        if 'no feedback' in low or 'in progress' in low:
            count += 1
            print(f"[{count}] Job {j.get('id')}: {repr(fb[:80])}")
            if count >= 15:
                break
    if count >= 15:
        break
