import sqlite3
import json
import re

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
truly_established_missing = []

for jid, raw in c.execute('SELECT job_id, job_json FROM jobs'):
    d = json.loads(raw)
    h = d.get('client_recent_history') or []
    if len(h) == 0:
        cl = d.get('client') or {}
        sp = (d.get('client_total_spent') or cl.get('total_spent') or '').replace(' ', '').lower()
        hr = (d.get('client_hire_rate') or cl.get('hire_rate') or '').replace(' ', '').lower()
        
        # Check spend: must be > 0 (e.g. not $0, not $0spent, not empty)
        m_sp = re.search(r'\$([\d,]+(?:\.\d+)?[km]?)', sp)
        has_real_spend = False
        if m_sp:
            val = m_sp.group(1).lower()
            if val not in ['0', '0.00']:
                has_real_spend = True
                
        # Check hire rate: must be > 0%
        m_hr = re.search(r'(\d+)%', hr)
        has_real_hires = False
        if m_hr and int(m_hr.group(1)) > 0:
            has_real_hires = True
            
        tot_hires = cl.get('total_hires') or ''
        m_th = re.search(r'(\d+)', tot_hires)
        if m_th and int(m_th.group(1)) > 0:
            has_real_hires = True
            
        if has_real_spend or has_real_hires:
            truly_established_missing.append((jid, d.get('job_title'), (d.get('posted_at') or '')[:10], sp, hr, d.get('job_url')))

print(f'Truly established clients missing history: {len(truly_established_missing)}')
print(f'Total jobs in 14-day DB: 20,652')
print(f'Jobs with Full Complete History / New Clients: {20652 - len(truly_established_missing):,} ({(20652 - len(truly_established_missing))/20652*100:.2f}%)')
by_date = {}
for r in truly_established_missing:
    dt = r[2] or 'No Date'
    by_date[dt] = by_date.get(dt, 0) + 1

print('\nBreakdown of truly missing established jobs by date:')
for dt in sorted(by_date.keys()):
    print(f'  {dt}: {by_date[dt]} jobs')

conn.close()
