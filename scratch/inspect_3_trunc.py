import sqlite3
import json
import re

conn = sqlite3.connect('output/database_today.db')
c = conn.cursor()
rows = c.execute('SELECT job_id, job_json, raw_html FROM jobs').fetchall()
conn.close()

for jid, jstr, raw_html in rows:
    d = json.loads(jstr)
    for r in d.get('client_recent_history', []):
        fb = r.get('feedback', '')
        if fb.endswith('...') or fb.endswith('\u2026'):
            print(f"Job {jid}: {fb}")
            clean_prefix = re.sub(r'[\s.…\u2026]+$', '', fb).strip()
            # Search in raw_html
            matches = [m.start() for m in re.finditer(re.escape(clean_prefix[:20]), raw_html)]
            for pos in matches:
                sample = raw_html[pos:pos+300]
                print(f"   Context in HTML: {repr(sample)}")
