import sqlite3

conn = sqlite3.connect("output/database_daily_2026-10-15.db")
tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
cols = conn.execute("PRAGMA table_info(jobs)").fetchall()
conn.close()
print("Tables:", tables)
print("Jobs Columns:", [c[1] for c in cols])
