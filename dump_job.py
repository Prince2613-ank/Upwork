import sqlite3, json, sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
row = c.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE job_id = ?", ('~022089338363935389527',)).fetchone()

data = json.loads(row[1])
for k, v in data.items():
    if k == 'raw_html':
        print(f"{k}: len={len(v) if v else 0}")
    elif k in ['description', 'full_description']:
        print(f"{k}: {repr(v[:100])}... (len {len(v)})")
    elif k == 'client_recent_history':
        print(f"{k}: count={len(v)}")
        for idx, item in enumerate(v):
            print(f"  [{idx}]: {item}")
    else:
        print(f"{k}: {v}")

print("raw_html in DB length:", len(row[2]) if row[2] else 0)
