import sqlite3
import re
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
db_job_ids = set(r[0] for r in c.execute('SELECT job_id FROM jobs').fetchall())
conn.close()

print(f"Total jobs in database_14days.db: {len(db_job_ids):,}")

# 1. Check raw_html files
raw_html_files = set(os.listdir('output/raw_html'))
has_raw_html_file = 0
for jid in db_job_ids:
    safe = jid.replace('~', '').replace('/', '_').replace(':', '_')
    if f"{safe}.html" in raw_html_files or f"{jid}.html" in raw_html_files:
        has_raw_html_file += 1

print(f"Jobs with raw_html file in output/raw_html: {has_raw_html_file:,} ({has_raw_html_file/len(db_job_ids)*100:.1f}%)")

# 2. Check collector.log URLs and collected titles
log_urls = {}
with open('output/logs/collector.log', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        if 'Navigating to https://www.upwork.com/jobs/' in line:
            m = re.search(r'(https://www.upwork.com/jobs/([^_]+)_~(0[0-9a-fA-F]+)/?)', line)
            if m:
                full_url = m.group(1)
                slug = m.group(2)
                jid = '~' + m.group(3)
                log_urls[jid] = (full_url, slug)

has_log_url = sum(1 for jid in db_job_ids if jid in log_urls)
print(f"Jobs with full URL & slug in collector.log: {has_log_url:,} ({has_log_url/len(db_job_ids)*100:.1f}%)")

# 3. Check combined coverage (either raw_html in DB, raw_html file, or log URL)
covered = 0
for jid in db_job_ids:
    safe = jid.replace('~', '').replace('/', '_').replace(':', '_')
    if f"{safe}.html" in raw_html_files or f"{jid}.html" in raw_html_files or jid in log_urls:
        covered += 1

print(f"Total jobs with full authentic title/URL sources: {covered:,} ({covered/len(db_job_ids)*100:.1f}%)")
