import sqlite3
import json
import re

conn = sqlite3.connect('output/database_yesterday.db')
c = conn.cursor()
rows = c.execute('SELECT job_id, job_json, raw_html FROM jobs').fetchall()
conn.close()

for jid, jstr, raw in rows:
    d = json.loads(jstr) if jstr else {}
    desc = (d.get('job', {}).get('description') or d.get('description') or '').strip()
    if not desc:
        print(f"Empty desc job: {jid}")
        if raw:
            m = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', raw, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group(1).strip())
                    # Find description string
                    for item in data:
                        if isinstance(item, str) and len(item) > 100 and ("looking for" in item.lower() or "we are" in item.lower() or "responsibilities" in item.lower() or "project" in item.lower()):
                            print(f"  Recoverable Nuxt desc: {repr(item[:80])}...")
                            break
                except Exception as e:
                    print(f"  Nuxt error: {e}")
