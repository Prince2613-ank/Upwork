import re, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

html_path = 'output/upwork_intelligence_report.html'
print(f"Reading {html_path}...")

with open(html_path, 'r', encoding='utf-8', errors='replace') as f:
    html = f.read()

print(f"HTML size: {len(html) / 1024 / 1024:.2f} MB")

# 1. Extract JOBS JSON
m = re.search(r'const JOBS = (\[.*?\]);\s*let filteredJobs', html, re.DOTALL)
if not m:
    print("ERROR: Could not find `const JOBS = [...]` in HTML!")
    sys.exit(1)

jobs_raw = m.group(1)
jobs = json.loads(jobs_raw)
print(f"Total jobs embedded in HTML: {len(jobs):,}")

# --- CHECK 1: Untitled jobs / error titles ---
bad_titles = []
for i, j in enumerate(jobs):
    t = (j.get('title') or '').strip()
    tl = t.lower()
    if not t or 'untitled job' in tl or 'job not found' in tl or "we'll be right back" in tl or "we’ll be right back" in tl:
        bad_titles.append((i, j.get('id'), t))

print(f"\n--- CHECK 1: TITLES ---")
print(f"Total bad/placeholder/untitled titles: {len(bad_titles)}")
for bt in bad_titles[:10]:
    print(f"  Job {bt[1]}: '{bt[2]}'")

# --- CHECK 2: Boolean reviews ---
print(f"\n--- CHECK 2: BOOLEAN REVIEWS ---")
boolean_reviews = []
total_reviews = 0
no_comment_reviews = 0
for i, j in enumerate(jobs):
    revs = j.get('reviews') or []
    total_reviews += len(revs)
    for r in revs:
        fb = str(r.get('feedback') or '').strip()
        if fb.lower() in ['true', 'false']:
            boolean_reviews.append((j.get('id'), fb))
        elif 'no comment' in fb.lower() or 'no feedback' in fb.lower():
            no_comment_reviews += 1

print(f"Total reviews across all jobs: {total_reviews:,}")
print(f"Reviews with exact boolean 'True'/'False': {len(boolean_reviews)}")
print(f"Reviews with 'No comment' / 'No feedback': {no_comment_reviews:,} ({no_comment_reviews/max(1, total_reviews)*100:.1f}%)")

# --- CHECK 3: Review perspective (Freelancer vs Client) ---
print(f"\n--- CHECK 3: REVIEW PERSPECTIVE (Freelancer review vs Client review) ---")
mention_client = 0
mention_freelancer = 0
sample_reviews = []
for j in jobs:
    for r in (j.get('reviews') or []):
        fb = str(r.get('feedback') or '')
        if len(sample_reviews) < 5 and len(fb) > 40 and 'no comment' not in fb.lower():
            sample_reviews.append((j.get('id'), r.get('job_title'), fb))

print("Sample non-empty reviews displayed in HTML:")
for sr in sample_reviews:
    print(f"  Parent Job {sr[0]} | Past: {sr[1]}")
    print(f"    Feedback snippet: {sr[2][:150]}...")

# --- CHECK 4: Client details ---
print(f"\n--- CHECK 4: CLIENT DETAILS ---")
stats = {
    'spend': 0,
    'rating': 0,
    'location': 0,
    'jobs_posted': 0,
    'hire_rate': 0,
    'total_hires': 0,
    'active_hires': 0,
    'hours_billed': 0,
    'member_since': 0,
}
for j in jobs:
    for k in stats:
        v = str(j.get(k) or '').strip()
        if v and v != 'N/A' and v != 'Unknown':
            stats[k] += 1

for k, count in stats.items():
    print(f"  Jobs with non-empty '{k}': {count:,} / {len(jobs):,} ({count/len(jobs)*100:.1f}%)")

