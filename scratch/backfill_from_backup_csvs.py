import sqlite3
import json
import csv
import glob

# Load reviews from all backup CSVs
all_csvs = ['output/client_history_backup.csv'] + glob.glob('output_backup*/**/client_history*.csv', recursive=True)
backup_reviews = {}

for cp in all_csvs:
    try:
        with open(cp, 'r', encoding='utf-8-sig', errors='ignore') as f:
            reader = csv.DictReader(f)
            for r in reader:
                pid = (r.get('parent_job_id') or '').strip()
                if pid:
                    norm = pid.replace('~02', '').replace('~', '')
                    item = {
                        'job_title': r.get('history_job_title') or 'Contract Completed',
                        'job_url': r.get('history_job_url', ''),
                        'date': r.get('date', ''),
                        'duration': r.get('duration', ''),
                        'payment_type': r.get('payment_type', ''),
                        'amount': (r.get('amount') or '').strip(),
                        'rating': (r.get('rating') or '').strip(),
                        'freelancer_name': (r.get('freelancer_name') or '').strip(),
                        'feedback': (r.get('feedback') or '').strip() or 'No feedback given',
                        'feedback_full': True
                    }
                    for k in [pid, norm, f"~{norm}", f"~02{norm}"]:
                        if k not in backup_reviews:
                            backup_reviews[k] = []
                        backup_reviews[k].append(item)
    except Exception as e:
        print(f'Error reading {cp}: {e}')

print(f'Loaded backup reviews for {len(backup_reviews):,} keys.')

# Update database_14days.db
conn = sqlite3.connect('output/database_14days.db', timeout=30)
c = conn.cursor()
c.execute("PRAGMA busy_timeout = 30000")
c.execute("PRAGMA journal_mode = WAL")

updated_14 = 0
for idx, (jid, raw) in enumerate(c.execute('SELECT job_id, job_json FROM jobs').fetchall(), 1):
    d = json.loads(raw)
    h = d.get('client_recent_history') or []
    if len(h) == 0:
        norm = jid.replace('~02', '').replace('~', '')
        if jid in backup_reviews or norm in backup_reviews:
            d['client_recent_history'] = backup_reviews.get(jid) or backup_reviews.get(norm)
            c.execute('UPDATE jobs SET job_json = ? WHERE job_id = ?', (json.dumps(d), jid))
            updated_14 += 1
            if updated_14 % 50 == 0:
                conn.commit()

conn.commit()
conn.close()
print(f'Backfilled {updated_14} additional jobs in database_14days.db!')

# Also update database.db
conn_m = sqlite3.connect('output/database.db', timeout=30)
cm = conn_m.cursor()
cm.execute("PRAGMA busy_timeout = 30000")
cm.execute("PRAGMA journal_mode = WAL")

updated_m = 0
for idx, (jid, raw) in enumerate(cm.execute('SELECT job_id, job_json FROM jobs').fetchall(), 1):
    d = json.loads(raw)
    h = d.get('client_recent_history') or []
    if len(h) == 0:
        norm = jid.replace('~02', '').replace('~', '')
        if jid in backup_reviews or norm in backup_reviews:
            d['client_recent_history'] = backup_reviews.get(jid) or backup_reviews.get(norm)
            cm.execute('UPDATE jobs SET job_json = ? WHERE job_id = ?', (json.dumps(d), jid))
            updated_m += 1
            if updated_m % 50 == 0:
                conn_m.commit()

conn_m.commit()
conn_m.close()
print(f'Backfilled {updated_m} additional jobs in database.db!')
