import sqlite3
import json
from collections import Counter

conn = sqlite3.connect('file:output/database_1week.db?mode=ro', uri=True)
cur = conn.cursor()

cur.execute('SELECT COUNT(*) FROM jobs')
total = cur.fetchone()[0]

cur.execute('SELECT job_json FROM jobs')
rows = cur.fetchall()
conn.close()

dates = Counter()
countries = Counter()
empty_desc_count = 0
total_reviews = 0

for (raw,) in rows:
    try:
        data = json.loads(raw)
        dt = data.get('posted_at')
        if dt:
            dates[dt[:10]] += 1
        else:
            dates['None'] += 1

        loc = data.get('client_location') or (data.get('client') or {}).get('location') or 'Unknown'
        # Normalize location string if needed
        countries[loc] += 1

        desc = (data.get('job') or {}).get('description') or ''
        if not desc or len(desc.strip()) < 20:
            empty_desc_count += 1

        hist = data.get('client_recent_history') or []
        total_reviews += len(hist)
    except Exception as e:
        pass

print(f'\n================ 1-WEEK AUDIT (2026-09-28 to 2026-10-04) ================')
print(f'TOTAL VERIFIED JOBS IN DATABASE: {total:,}')
print(f'EMPTY / TRUNCATED DESCRIPTIONS: {empty_desc_count} (Completeness: {(total - empty_desc_count)/total*100:.1f}%)')
print(f'TOTAL FREELANCER REVIEWS CAPTURED: {total_reviews:,}')
print('\nDATE BREAKDOWN:')
for dt in sorted(dates.keys()):
    print(f'  {dt}: {dates[dt]:,} jobs')

print(f'\nTOP CLIENT COUNTRIES (Total unique locations: {len(countries)}):')
for loc, cnt in countries.most_common(25):
    print(f'  - {loc}: {cnt:,} jobs')
print('========================================================================\n')
