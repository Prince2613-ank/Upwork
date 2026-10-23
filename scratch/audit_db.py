import sqlite3, json

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
total = c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
detail_fetched = c.execute("SELECT COUNT(*) FROM jobs WHERE job_json IS NOT NULL AND LENGTH(job_json) > 100").fetchone()[0]
hist_count = 0
no_hist_count = 0
no_hist_new_client = 0
no_hist_old_client = 0
sample_missing = []
sample_ok = []

for jid, raw in c.execute('SELECT job_id, job_json FROM jobs'):
    data = json.loads(raw) if raw else {}
    hist = data.get('client_recent_history') or []
    cl = data.get('client') or {}
    
    if len(hist) > 0:
        hist_count += 1
        if len(sample_ok) < 3:
            sample_ok.append({'id': jid, 'hist_count': len(hist), 'title': data.get('title', '')[:40]})
    else:
        no_hist_count += 1
        # Check if new client (no jobs posted)
        jobs_posted = cl.get('jobs_posted', '') or ''
        try:
            jobs_posted_int = int(str(jobs_posted).replace(',', ''))
        except:
            jobs_posted_int = 0
        
        if jobs_posted_int <= 1:
            no_hist_new_client += 1
        else:
            no_hist_old_client += 1
            if len(sample_missing) < 5:
                sample_missing.append({
                    'id': jid,
                    'title': data.get('title', '')[:40],
                    'jobs_posted': jobs_posted,
                    'client_keys': list(cl.keys())[:6],
                    'has_about_text': bool(cl.get('about_client_text'))
                })

conn.close()

print(f'Total jobs: {total}')
print(f'Detail fetched (json > 100 bytes): {detail_fetched}')
print(f'With history: {hist_count} ({hist_count/total*100:.1f}%)')
print(f'Without history: {no_hist_count} ({no_hist_count/total*100:.1f}%)')
print(f'  - New clients (<=1 job posted): {no_hist_new_client}')
print(f'  - Established clients missing history: {no_hist_old_client}')
print()
print('Sample WITH history:')
for s in sample_ok:
    print(f'  {s}')
print()
print('Sample MISSING history (established clients):')
for s in sample_missing:
    print(f'  {s}')
