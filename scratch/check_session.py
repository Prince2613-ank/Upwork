import sqlite3

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
c = conn.cursor()
c.execute("SELECT COUNT(*), MIN(saved_at), MAX(saved_at) FROM jobs WHERE saved_at >= '2026-10-05 07:04:00'")
res = c.fetchone()
print(f"Jobs saved in this session (since 12:34 IST): {res[0]} jobs (first: {res[1]}, latest: {res[2]})")

# Also check distinct locations in this session
c.execute("SELECT job_json FROM jobs WHERE saved_at >= '2026-10-05 07:04:00'")
import json
countries = set()
for (raw,) in c.fetchall():
    d = json.loads(raw)
    loc = d.get("client_location") or ""
    countries.add(loc.split()[0] if loc else "Unknown")
print(f"Distinct client countries active in this session: {countries}")
conn.close()
