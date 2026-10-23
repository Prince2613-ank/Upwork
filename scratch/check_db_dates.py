import sqlite3

conn = sqlite3.connect("file:output/database_1week.db?mode=ro", uri=True)
cur = conn.cursor()
cur.execute("PRAGMA table_info(jobs)")
cols = [r[1] for r in cur.fetchall()]
print("Columns in jobs:", cols)

date_col = 'actual_dt' if 'actual_dt' in cols else ('posted_date' if 'posted_date' in cols else 'posted')
print("Using date col:", date_col)

cur.execute(f"SELECT SUBSTR({date_col}, 1, 10) as dt, count(*) FROM jobs GROUP BY dt ORDER BY dt DESC")
for dt, count in cur.fetchall():
    print(f"  {dt}: {count}")

cur.execute("SELECT count(*) FROM jobs")
print("Total jobs:", cur.fetchone()[0])
