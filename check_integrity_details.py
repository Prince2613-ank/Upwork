import sqlite3
import json
import re
from pathlib import Path

db_path = Path("output/database_1week.db")
if not db_path.exists():
    print("Database does not exist:", db_path)
    exit(1)

conn = sqlite3.connect(str(db_path))
c = conn.cursor()

tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print(f"Tables in {db_path}: {tables}")
for t in tables:
    cnt = c.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
    print(f"  Table '{t}': {cnt:,} rows")

rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
conn.close()

print(f"\nTotal jobs in database: {len(rows):,}")

# Check data fields
total_jobs = len(rows)
empty_title = 0
empty_desc = 0
empty_url = 0
empty_location = 0
mismatched_title_url = 0
jobs_with_reviews = 0
total_reviews = 0
reviews_empty_feedback = 0
reviews_short_feedback = 0

sample_mismatches = []
slug_title_mismatches = []

for idx, (jid, jjson) in enumerate(rows):
    try:
        data = json.loads(jjson)
    except Exception as e:
        print(f"Error parsing json for {jid}: {e}")
        continue
    
    job_dict = data.get("job") or {}
    client_dict = data.get("client") or {}
    
    title = (data.get("job_title") or job_dict.get("title") or data.get("title") or "").strip()
    desc = (job_dict.get("description") or data.get("description") or "").strip()
    url = (data.get("job_url") or "").strip()
    loc = (client_dict.get("location") or data.get("client_location") or "").strip()
    
    if not title:
        empty_title += 1
    if not desc:
        empty_desc += 1
    if not url:
        empty_url += 1
    if not loc:
        empty_location += 1
        
    # Check title vs URL slug
    # URL format: https://www.upwork.com/jobs/slug_~jid
    if url and "~" in url:
        m = re.search(r'/jobs/([^_/?#]+)_~', url)
        if m:
            slug = m.group(1).lower().replace('-', ' ').replace('_', ' ')
            title_clean = re.sub(r'[^a-zA-Z0-9\s]', '', title.lower()).strip()
            slug_clean = re.sub(r'[^a-zA-Z0-9\s]', '', slug).strip()
            # If slug words are completely distinct from title words
            title_words = set(title_clean.split())
            slug_words = set(slug_clean.split())
            common = title_words.intersection(slug_words)
            if slug_words and len(common) == 0 and len(slug_words) > 2 and len(title_words) > 2:
                slug_title_mismatches.append({
                    "job_id": jid,
                    "title": title,
                    "slug": slug,
                    "url": url
                })

    hist = data.get("client_recent_history") or []
    if hist:
        jobs_with_reviews += 1
        total_reviews += len(hist)
        for h in hist:
            fb = (h.get("feedback") or "").strip()
            if not fb:
                reviews_empty_feedback += 1
            elif len(fb) < 10:
                reviews_short_feedback += 1

print("\n--- INTEGRITY AUDIT SUMMARY ---")
print(f"Empty Titles: {empty_title}")
print(f"Empty Descriptions: {empty_desc}")
print(f"Empty URLs: {empty_url}")
print(f"Empty Locations: {empty_location}")
print(f"Jobs with Client Feedback History: {jobs_with_reviews:,} ({jobs_with_reviews/total_jobs*100:.1f}%)")
print(f"Total Feedback Records: {total_reviews:,}")
print(f"Empty Feedback Records: {reviews_empty_feedback:,}")
print(f"Short (<10 chars) Feedback Records: {reviews_short_feedback:,}")
print(f"Slug-Title Divergences: {len(slug_title_mismatches)}")

if slug_title_mismatches:
    print("\nSample Slug-Title Divergences (first 5):")
    for s in slug_title_mismatches[:5]:
        print(f"  ID: {s['job_id']}")
        print(f"    Title: {s['title']}")
        print(f"    Slug:  {s['slug']}")
        print(f"    URL:   {s['url']}")
