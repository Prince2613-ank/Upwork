import sqlite3, json
from pathlib import Path

DB = Path(r'C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\output\database.db')
rows = sqlite3.connect(DB).execute('SELECT job_id, job_json FROM jobs').fetchall()
best = max(rows, key=lambda r: len(json.loads(r[1]).get('client_recent_history') or []))
d = json.loads(best[1])
hist = d.get('client_recent_history') or []
print("Job:", d.get('job_title','')[:60])
print("History count:", len(hist))
print("\nSample history[0] keys and values:")
h0 = hist[0]
for k, v in h0.items():
    print(f"  {k}: {str(v)[:200]}")

print("\nSample item WITH full feedback:")
for h in hist:
    fb = h.get('feedback_full') or h.get('feedback') or ''
    if fb and len(str(fb)) > 30:
        for k, v in h.items():
            print(f"  {k}: {str(v)[:200]}")
        break

# Also check client keys
client = d.get('client') or {}
print("\nClient all fields:")
for k, v in client.items():
    print(f"  {k}: {str(v)[:200]}")
