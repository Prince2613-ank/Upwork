import json
import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('upwork_14days_fetched_report.html', 'r', encoding='utf-8') as f:
    text = f.read()

m = re.search(r'const JOBS = (\[.*?\]);\s*let filteredJobs', text, re.DOTALL)
if m:
    jobs = json.loads(m.group(1))
    print(f"Total jobs in HTML payload: {len(jobs):,}")
    target = None
    for j in jobs:
        if j.get('id') == '~022089338363935389527':
            target = j
            break
    if target:
        print("\n=== TARGET JOB RECORD IN HTML ===")
        print("ID:           ", target.get('id'))
        print("Title:        ", repr(target.get('title')))
        print("URL:          ", repr(target.get('url')))
        print("Location:     ", repr(target.get('location')))
        print("Budget:       ", repr(target.get('budget')))
        print("Type:         ", repr(target.get('budget_type')))
        print("Desc Length:  ", len(target.get('description', '')))
        print("Total Reviews:", target.get('total_reviews'))
        print("Reviews List:")
        for idx, r in enumerate(target.get('reviews', [])):
            print(f"  [{idx+1}] {r.get('job_title')} | {r.get('rating')}★ | {r.get('amount')} | {r.get('freelancer')} | {repr(r.get('feedback'))}")
    else:
        print("Target job not found in HTML!")
else:
    print("Could not find JOBS payload in HTML")
