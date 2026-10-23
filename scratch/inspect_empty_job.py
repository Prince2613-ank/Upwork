import sqlite3
import json
import glob
import sys

sys.stdout.reconfigure(encoding='utf-8')

target_jid = "022111270348951686753"

for db in glob.glob("output/*.db"):
    try:
        conn = sqlite3.connect(db)
        r = conn.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE job_id LIKE ?", (f"%{target_jid}%",)).fetchone()
        if r:
            print(f"=== FOUND IN {db} ===")
            print(f"Job ID: {r[0]}")
            raw_html = r[2] or ""
            print(f"raw_html length: {len(raw_html)}")
            if raw_html:
                print("raw_html preview (first 300 chars):", repr(raw_html[:300]))
                if "error 1015" in raw_html.lower():
                    print("--> CONTAINS ERROR 1015 / RATE LIMIT!")
                if "login" in raw_html.lower() and "sign in" in raw_html.lower():
                    print("--> CONTAINS LOGIN SCREEN!")
            d = json.loads(r[1])
            print("Job Dict Keys:", list(d.keys()))
            desc = d.get('description') or (d.get('job') or {}).get('description') or ''
            print(f"Description length: {len(desc)} -> {repr(desc[:100])}")
            print(f"Client dict: {d.get('client')}")
            print(f"Client location: {d.get('client_location')}")
            revs = d.get('client_recent_history') or []
            print(f"Reviews count: {len(revs)}")
        conn.close()
    except Exception as e:
        pass
