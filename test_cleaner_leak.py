import sqlite3
import json

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

from generate_standalone_report import clean_freelancer_review

client_to_fl_samples = []

for jid, jj in rows:
    d = json.loads(jj)
    hist = d.get("client_recent_history") or []
    for h in hist:
        fb = h.get("feedback") or ""
        fl = h.get("freelancer_name") or ""
        fb_lower = fb.lower()
        if any(pat in fb_lower for pat in ["the freelancer", "this freelancer", "he is a great", "she is a great", "he did", "she did", "his work", "her work"]):
            # Check if it was supposed to be cleaned
            res = clean_freelancer_review(fb, fl)
            if res:
                client_to_fl_samples.append((jid, fl, fb))

print(f"Total reviews matching client-to-freelancer patterns that passed cleaner: {len(client_to_fl_samples)}")
print("\nFirst 5 samples:")
for jid, fl, fb in client_to_fl_samples[:5]:
    print(f"  Job {jid} | Freelancer: {fl}")
    print(f"    Feedback: {repr(fb)}")
