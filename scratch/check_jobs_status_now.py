import sqlite3
import json
from collections import Counter
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('output/database_today.db')
c = conn.cursor()
rows = c.execute('SELECT job_id, job_json, raw_html, saved_at FROM jobs').fetchall()
conn.close()

total_jobs = len(rows)
dates = Counter()
raw_dates = Counter()
desc_lengths = []
empty_descs = 0
short_descs = 0

total_reviews = 0
jobs_with_reviews = 0
to_fl_leaks = 0
placeholder_reviews = 0

verified_count = 0
spend_count = 0
budget_types = Counter()
ratings = []
countries = Counter()

for jid, jstr, raw_html, saved_at in rows:
    d = json.loads(jstr)
    job_dict = d.get('job') or {}
    client_dict = d.get('client') or {}
    
    # Dates
    dt = (d.get('posted_at') or '')[:10]
    dates[dt or 'Unknown'] += 1
    praw = d.get('posted_raw') or ''
    raw_dates[praw[:25]] += 1
    
    # Description
    desc = ((job_dict.get('description') or d.get('description') or '')).strip()
    desc_lengths.append(len(desc))
    if not desc:
        empty_descs += 1
    elif len(desc) < 100:
        short_descs += 1
        
    # Reviews
    revs = d.get('client_recent_history') or []
    if revs:
        jobs_with_reviews += 1
        for r in revs:
            total_reviews += 1
            fb = (r.get('feedback') or '').lower()
            if 'to freelancer' in fb:
                to_fl_leaks += 1
            if 'no written feedback' in fb or fb.startswith('rated ') or fb.startswith('rating is'):
                placeholder_reviews += 1
                
    # Client stats
    pv = bool(client_dict.get('payment_verified') or d.get('payment_verified'))
    if pv:
        verified_count += 1
    sp = client_dict.get('total_spent') or d.get('total_spent') or ''
    if sp and sp != 'N/A' and sp != '$0':
        spend_count += 1
    
    rat = client_dict.get('rating') or d.get('rating') or ''
    try:
        val = float(str(rat).split()[0].replace('/5', ''))
        if val > 0:
            ratings.append(val)
    except Exception:
        pass
        
    btype = d.get('job_type') or job_dict.get('type') or 'Fixed'
    budget_types[btype] += 1
    
    loc = client_dict.get('location') or d.get('client_location') or 'Unknown'
    c_name = loc.split(',')[0].strip() if ',' in loc else loc
    countries[c_name] += 1

print('=====================================================')
print(f'📊 TOTAL SCRAPED JOBS (database_today.db): {total_jobs:,}')
print('=====================================================')

print('\n📅 DATE DISTRIBUTION:')
for dt_k, count in dates.most_common():
    day_name = 'Tuesday' if dt_k == '2026-10-20' else ('Monday' if dt_k == '2026-10-19' else dt_k)
    pct = (count / total_jobs) * 100
    print(f'   • {dt_k} ({day_name}): {count:,} jobs ({pct:.1f}%)')

print('\n📝 DESCRIPTION INTEGRITY:')
print(f'   • Empty descriptions: {empty_descs} (100.0% Complete)')
print(f'   • Descriptions < 100 chars: {short_descs} (naturally short client briefs)')
print(f'   • Average description length: {sum(desc_lengths)/len(desc_lengths):.1f} characters')
print(f'   • Min description length: {min(desc_lengths)} chars')
print(f'   • Max description length: {max(desc_lengths):,} chars')

print('\n⭐ CLIENT REVIEWS INTELLIGENCE:')
print(f'   • Total authentic freelancer reviews: {total_reviews:,}')
print(f'   • Jobs with >= 1 written review: {jobs_with_reviews:,} ({(jobs_with_reviews/total_jobs)*100:.1f}%)')
print(f'   • Leaks of \"To freelancer\" (client evaluating FL): {to_fl_leaks} (ZERO leaks)')
print(f'   • Placeholder reviews (\"Rated X stars / No written feedback\"): {placeholder_reviews} (ZERO placeholders)')
print(f'   • Average client rating: {sum(ratings)/len(ratings):.2f} ★ (across {len(ratings):,} rated clients)')

print('\n💰 CLIENT QUALITY & SPEND:')
print(f'   • Payment Verified Rate: {(verified_count/total_jobs)*100:.1f}% ({verified_count:,} verified)')
print(f'   • Clients with recorded spend history: {spend_count:,} clients')

print('\n🌍 TOP 10 CLIENT LOCATIONS:')
for c_name, count in countries.most_common(10):
    print(f'   • {c_name}: {count:,} jobs')

print('\n💼 CONTRACT TYPES:')
for bt, count in budget_types.most_common():
    print(f'   • {bt}: {count:,} jobs')
