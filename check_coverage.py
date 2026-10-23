import sqlite3, json
from collections import defaultdict
from collector.config.settings import DEFAULT_LOCATIONS

conn = sqlite3.connect('output/database.db')
c = conn.cursor()
rows = c.execute('SELECT job_json FROM jobs').fetchall()

loc_stats = {loc: {'count': 0, 'oldest': None, 'newest': None} for loc in DEFAULT_LOCATIONS}
unmatched = 0

for r in rows:
    try:
        j = json.loads(r[0])
        cloc = j.get('client', {}).get('location', '') or ''
        posted = j.get('posted_at', '') or ''
        
        matched = False
        for loc in DEFAULT_LOCATIONS:
            if loc.lower() in cloc.lower() or (loc == 'United States' and ('United States' in cloc or 'USA' in cloc)):
                matched = True
                loc_stats[loc]['count'] += 1
                if posted:
                    if loc_stats[loc]['oldest'] is None or posted < loc_stats[loc]['oldest']:
                        loc_stats[loc]['oldest'] = posted
                    if loc_stats[loc]['newest'] is None or posted > loc_stats[loc]['newest']:
                        loc_stats[loc]['newest'] = posted
                break
        if not matched:
            unmatched += 1
    except Exception:
        pass

print("=" * 80)
print(f"{'Idx':3s} | {'Location':30s} | {'Count':6s} | {'Oldest Date':12s} | {'Newest Date':12s}")
print("=" * 80)
for i, loc in enumerate(DEFAULT_LOCATIONS):
    st = loc_stats[loc]
    old_d = str(st['oldest'])[:10] if st['oldest'] else "None"
    new_d = str(st['newest'])[:10] if st['newest'] else "None"
    print(f"{i:3d} | {loc[:30]:30s} | {st['count']:6d} | {old_d:12s} | {new_d:12s}")
print(f"Other / Unmatched: {unmatched}")
print(f"Total jobs in DB: {len(rows)}")
