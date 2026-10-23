import sqlite3
import json
import time

conn = sqlite3.connect('output/database_today.db')
cur = conn.cursor()
c_all = cur.execute('SELECT count(*) FROM jobs').fetchone()[0]
c_1m = cur.execute("SELECT count(*) FROM jobs WHERE saved_at >= datetime('now', '-1 minute')").fetchone()[0]
c_2m = cur.execute("SELECT count(*) FROM jobs WHERE saved_at >= datetime('now', '-2 minutes')").fetchone()[0]
c_3m = cur.execute("SELECT count(*) FROM jobs WHERE saved_at >= datetime('now', '-3 minutes')").fetchone()[0]
conn.close()

with open('output/scraper_live_status.json', 'r', encoding='utf-8') as f:
    status = json.load(f)

print(f"DATABASE TOTAL: {c_all} jobs")
print(f"LAST 1 MINUTE SAVES: {c_1m} jobs")
print(f"LAST 2 MINUTES SAVES: {c_2m} jobs ({c_2m/2.0:.1f} jobs/min)")
print(f"LAST 3 MINUTES SAVES: {c_3m} jobs ({c_3m/3.0:.1f} jobs/min)")
print(f"LIVE TELEMETRY SPEED: {status.get('rate_per_min')} jobs/min")
print(f"WORKER A: Page {status.get('worker_a', {}).get('page')}, Saved {status.get('worker_a', {}).get('saved')}, Action: {status.get('worker_a', {}).get('action')}")
print(f"WORKER B: Page {status.get('worker_b', {}).get('page')}, Saved {status.get('worker_b', {}).get('saved')}, Action: {status.get('worker_b', {}).get('action')}")
