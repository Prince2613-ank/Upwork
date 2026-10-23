import sqlite3
import json
import re

conn = sqlite3.connect("output/database_1week.db")
c = conn.cursor()
# Only select job_id, job_json to avoid reading 7GB of raw_html
rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

print(f"Total rows fetched: {len(rows)}")

# 1. Check for duplicate job_ids
job_ids = [r[0] for r in rows]
unique_jids = set(job_ids)
print(f"Unique job IDs: {len(unique_jids)} (Duplicates: {len(job_ids) - len(unique_jids)})")

# 2. Check title vs URL and title vs Description
url_mismatches = 0
weird_titles = 0
client_reviewing_freelancer_in_feedback = 0
empty_reviews = 0
total_reviews = 0

sample_review_texts = []

for jid, jjson in rows:
    data = json.loads(jjson)
    title = data.get("job_title") or data.get("title") or ""
    url = data.get("job_url") or ""
    desc = data.get("description") or (data.get("job") or {}).get("description") or ""
    hist = data.get("client_recent_history") or []
    
    # Check if title looks like a review or error
    if any(bad in title.lower() for bad in ["rating is", "no feedback", "page not found", "access denied", "just a moment", "completed project"]):
        weird_titles += 1
        print(f"Weird title found: {jid} -> {title}")
        
    for h in hist:
        total_reviews += 1
        fb = (h.get("feedback") or "").strip()
        fl = (h.get("freelancer_name") or "").strip()
        
        # Check if feedback looks like client reviewing freelancer
        # e.g., "he was great", "she did a good job", "the freelancer", "great freelancer"
        fb_lower = fb.lower()
        if any(pat in fb_lower for pat in ["the freelancer", "this freelancer", "he is a great", "she is a great", "he did", "she did", "his work", "her work"]):
            client_reviewing_freelancer_in_feedback += 1
            if len(sample_review_texts) < 10:
                sample_review_texts.append((jid, fl, fb))

print(f"Weird titles: {weird_titles}")
print(f"Total reviews in database: {total_reviews}")
print(f"Reviews where text appears to be CLIENT reviewing FREELANCER: {client_reviewing_freelancer_in_feedback}")

print("\nSample reviews where client reviews freelancer:")
for jid, fl, fb in sample_review_texts[:5]:
    print(f"  Job {jid} (Freelancer: {fl}):")
    print(f"    Feedback: {fb[:100]}...")
