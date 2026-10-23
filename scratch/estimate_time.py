import urllib.request
import json
import sqlite3
import time
from datetime import datetime

# 1. Telemetry
try:
    with urllib.request.urlopen('http://127.0.0.1:8000/api/scraper/telemetry', timeout=2) as r:
        telem = json.loads(r.read().decode())
except Exception as e:
    telem = {'error': str(e)}

# 2. Daily DB stats
conn = sqlite3.connect('output/database_daily_2026-10-15.db')
c = conn.cursor()
c.execute('SELECT COUNT(*) FROM jobs')
total_jobs = c.fetchone()[0]

# Check latest jobs
c.execute("SELECT job_id, saved_at FROM jobs ORDER BY rowid DESC LIMIT 5")
recent_jobs = c.fetchall()

# Check country distribution
c.execute("SELECT COUNT(DISTINCT json_extract(job_json, '$.client_location')) FROM jobs")
unique_locs = c.fetchone()[0]

conn.close()

print(json.dumps({
    'daily_db_total': total_jobs,
    'unique_locations': unique_locs,
    'telemetry': telem,
    'latest_5_saves': recent_jobs
}, indent=2))
