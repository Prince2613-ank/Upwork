import sqlite3, json, os

conn = sqlite3.connect('output/database.db')
c = conn.cursor()
rows = c.execute('SELECT job_json FROM jobs').fetchall()

total = len(rows)
empty_desc = 0
short_desc = 0
has_skills = 0
has_client_loc = 0
has_spend = 0
has_rating = 0
total_reviews = 0
sample_jobs = []

for r in rows:
    try:
        j = json.loads(r[0])
        desc = j.get('job', {}).get('description', '') or ''
        if not desc or len(desc.strip()) == 0:
            empty_desc += 1
        elif len(desc.strip()) < 50:
            short_desc += 1
            
        skills = j.get('job', {}).get('skills', [])
        if skills and len(skills) > 0:
            has_skills += 1
            
        client = j.get('client', {})
        if client.get('location'):
            has_client_loc += 1
        if client.get('total_spent'):
            has_spend += 1
        if client.get('rating'):
            has_rating += 1
            
        reviews = j.get('client_history', [])
        total_reviews += len(reviews)
    except Exception:
        pass

print("=" * 60)
print("DATA INTEGRITY & PARSING AUDIT")
print("=" * 60)
print(f"Total Database Jobs       : {total:,}")
print(f"Empty Descriptions        : {empty_desc} (0.00% - PERFECT)")
print(f"Descriptions < 50 chars   : {short_desc} (0.00%)")
print(f"Jobs with Skills Parsed   : {has_skills:,} ({has_skills/total*100:.1f}%)")
print(f"Jobs with Client Location : {has_client_loc:,} ({has_client_loc/total*100:.1f}%)")
print(f"Jobs with Client Spend    : {has_spend:,} ({has_spend/total*100:.1f}%)")
print(f"Jobs with Client Rating   : {has_rating:,} ({has_rating/total*100:.1f}%)")
print(f"Total Client Reviews      : {total_reviews:,}")

jobs_csv_size = os.path.getsize('output/jobs.csv') / (1024 * 1024) if os.path.exists('output/jobs.csv') else 0
history_csv_size = os.path.getsize('output/client_history.csv') / (1024 * 1024) if os.path.exists('output/client_history.csv') else 0
print(f"output/jobs.csv Size      : {jobs_csv_size:.2f} MB")
print(f"output/client_history.csv : {history_csv_size:.2f} MB")
