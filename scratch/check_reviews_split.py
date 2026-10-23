import sqlite3
import json
from pathlib import Path

DB_PATH = Path("output/database_yesterday.db")
conn = sqlite3.connect(DB_PATH)
rows = conn.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

import sys
sys.path.insert(0, ".")
from generate_standalone_report import clean_freelancer_review

with_rev = []
zero_rev = []

for jid, raw_j in rows:
    d = json.loads(raw_j)
    hist = d.get("client_recent_history") or []
    valid_revs = []
    for h in hist:
        fb = h.get("feedback") or ""
        fl = h.get("freelancer_name") or ""
        c = clean_freelancer_review(fb, fl)
        if c:
            valid_revs.append(c)
    if valid_revs:
        with_rev.append((jid, len(valid_revs)))
    else:
        zero_rev.append(jid)

print(f"Total jobs: {len(rows)}")
print(f"Jobs WITH verified freelancer reviews: {len(with_rev)} (Total reviews: {sum(x[1] for x in with_rev)})")
print(f"Jobs with 0 freelancer reviews: {len(zero_rev)}")
