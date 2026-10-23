import sqlite3
import json

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
rows = c.execute("SELECT job_id, (raw_html LIKE '%__NUXT_DATA__%') FROM jobs").fetchall()
conn.close()

with_nuxt = sum(1 for r in rows if r[1])
total = len(rows)
print(f"Total jobs: {total:,}")
print(f"Jobs with __NUXT_DATA__ in raw_html: {with_nuxt:,} ({with_nuxt/total*100:.1f}%)")
