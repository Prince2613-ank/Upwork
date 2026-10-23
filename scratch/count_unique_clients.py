import sqlite3
import json
import re

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
unique_clients = {}
jobs_to_fetch = []

for jid, raw in c.execute('SELECT job_id, job_json FROM jobs'):
    d = json.loads(raw)
    h = d.get('client_recent_history') or []
    if len(h) == 0:
        cl = d.get('client') or {}
        sp = (d.get('client_total_spent') or cl.get('total_spent') or '').replace(' ', '').lower()
        hr = (d.get('client_hire_rate') or cl.get('hire_rate') or '').replace(' ', '').lower()
        
        m_sp = re.search(r'\$([\d,]+(?:\.\d+)?[km]?)', sp)
        has_real_spend = m_sp and m_sp.group(1).lower() not in ['0', '0.00']
        m_hr = re.search(r'(\d+)%', hr)
        has_real_hires = m_hr and int(m_hr.group(1)) > 0
        tot_hires = cl.get('total_hires') or ''
        m_th = re.search(r'(\d+)', tot_hires)
        if m_th and int(m_th.group(1)) > 0:
            has_real_hires = True
            
        if has_real_spend or has_real_hires:
            since = cl.get('member_since') or ''
            loc = d.get('client_location') or cl.get('location') or ''
            posted = cl.get('jobs_posted') or ''
            fp = f'{since}|{sp}|{posted}|{loc}'
            if fp not in unique_clients:
                unique_clients[fp] = []
            unique_clients[fp].append((jid, d.get('job_title'), d.get('job_url')))
            jobs_to_fetch.append((jid, d.get('job_title'), d.get('job_url'), fp))

print(f'Total jobs needing history: {len(jobs_to_fetch)}')
print(f'Unique client profiles among them: {len(unique_clients)}')
conn.close()
