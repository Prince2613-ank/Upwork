import sqlite3
import json
import sys

db_path = "output/database_1week.db"
conn = sqlite3.connect(db_path, timeout=10)
c = conn.cursor()

cols = [r[1] for r in c.execute("PRAGMA table_info(jobs)").fetchall()]
print("Columns in jobs table:", cols)

has_raw = c.execute("SELECT count(*) FROM jobs WHERE raw_html IS NOT NULL AND length(raw_html) > 100").fetchone()[0]
print(f"Jobs with raw_html in DB: {has_raw}")

conn.close()
