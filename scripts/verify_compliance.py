import csv, os, json
from pathlib import Path

out_dir = Path('output')
jobs_csv = out_dir / 'jobs.csv'
hist_csv = out_dir / 'client_history.csv'
jobs_json = out_dir / 'jobs.json'
raw_dir = out_dir / 'raw_html'

print('=== 1. VERIFY JOBS.CSV ===')
with open(jobs_csv, 'r', encoding='utf-8-sig') as f:
    jobs = list(csv.DictReader(f))
print(f'Total jobs in CSV: {len(jobs)}')

missing_links = 0
missing_html_files = 0
for j in jobs:
    if not j.get('job_url') or not j.get('client_profile_url') or not j.get('reviews_anchor') or not j.get('raw_html_file'):
        missing_links += 1
    rel_html = j.get('raw_html_file')
    if rel_html:
        full_html = out_dir / rel_html
        if not full_html.exists() or full_html.stat().st_size == 0:
            missing_html_files += 1

print(f'Jobs with missing links: {missing_links}')
print(f'Jobs with missing or empty raw HTML file: {missing_html_files}')

print('\n=== 2. VERIFY CLIENT_HISTORY.CSV ===')
with open(hist_csv, 'r', encoding='utf-8-sig') as f:
    hist = list(csv.DictReader(f))
print(f'Total review records in CSV: {len(hist)}')

hist_missing_links = 0
for h in hist:
    if not h.get('parent_job_id') or not h.get('parent_job_url') or not h.get('client_profile_url') or not h.get('raw_html_file'):
        hist_missing_links += 1

print(f'History rows with missing relational links: {hist_missing_links}')

print('\n=== 3. VERIFY JOBS.JSON ===')
with open(jobs_json, 'r', encoding='utf-8') as f:
    jd = json.load(f)
j_list = jd.get('jobs', [])
print(f'Jobs in JSON: {len(j_list)}')
json_missing_links = 0
for j in j_list:
    links = j.get('links', {})
    if not links.get('client_profile_url') or not links.get('reviews_anchor') or not links.get('raw_html_file'):
        json_missing_links += 1
print(f'JSON jobs missing links: {json_missing_links}')

print('\n=== 4. TOTAL HTML FILES IN RAW_HTML ===')
html_files = list(raw_dir.glob('*.html'))
print(f'Total standalone HTML files: {len(html_files)}')
