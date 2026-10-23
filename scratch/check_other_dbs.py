import sqlite3, json
from collections import Counter

for db_name in ["output/database_14days.db", "output/database.db"]:
    try:
        conn = sqlite3.connect(f"file:{db_name}?mode=ro", uri=True)
        cur = conn.cursor()
        cur.execute("SELECT job_id, job_json FROM jobs")
        rows = cur.fetchall()
        dates = []
        for jid, raw_j in rows:
            try:
                d = json.loads(raw_j)
                p = d.get("posted_at") or d.get("posted_date") or d.get("job_posted_at") or ""
                if p:
                    dates.append(p[:10])
            except:
                pass
        c = Counter(dates)
        print(f"\n--- {db_name} (Total: {len(rows)}) ---")
        for k in sorted(c.keys(), reverse=True)[:15]:
            print(f"  {k}: {c[k]}")
    except Exception as e:
        print(f"Error reading {db_name}: {e}")
