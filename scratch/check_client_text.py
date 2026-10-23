import sqlite3, json

conn = sqlite3.connect('output/database.db')
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs LIMIT 10").fetchall()

for jid, raw in rows[:5]:
    d = json.loads(raw)
    client = d.get('client') or {}
    txt = client.get('about_client_text') or ''
    print('JID:', jid)
    print('about_client_text len:', len(txt))
    print('about_client_text preview:', repr(txt[:300]))
    print('-'*50)
