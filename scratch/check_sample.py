import sqlite3, json

conn = sqlite3.connect('output/database.db')
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs WHERE job_json LIKE '%Partner%Admin Dashboard%'").fetchall()

for jid, raw in rows:
    d = json.loads(raw)
    print('JID:', jid)
    print('Title:', d.get('job_title'))
    client = d.get('client') or {}
    print('Client keys:', list(client.keys()))
    for k, v in client.items():
        if k != 'reviews':
            print(f'  {k}: {repr(v)}')
    if d.get('client_recent_history'):
        print('client_recent_history count:', len(d.get('client_recent_history')))
        for h in d.get('client_recent_history')[:3]:
            print('  history item:', h)
