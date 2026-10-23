import re
import json
import sqlite3

html_path = "output/upwork_yesterday_with_reviews_only.html"
with open(html_path, "r", encoding="utf-8", errors="ignore") as f:
    text = f.read()

pos = text.find("Excellent collaboration! Everything went perfectly")
print(f"Position in HTML: {pos}")
if pos != -1:
    snippet_before = text[max(0, pos-4000):pos]
    id_matches = list(re.finditer(r'["\']id["\']:\s*["\']([^"\']+)["\']', snippet_before))
    if id_matches:
        job_id = id_matches[-1].group(1)
        print(f"Associated Job ID: {job_id}")
    else:
        print("No job ID found before snippet")
        job_id = None

    # Check the full object in html
    # Let's find title
    title_matches = list(re.finditer(r'["\']title["\']:\s*["\']([^"\']+)["\']', snippet_before))
    if title_matches:
        print(f"Title: {title_matches[-1].group(1)}")

# Check databases for this job ID or feedback
dbs = [
    "output/database_yesterday.db",
    "output/database_daily_2026-10-15.db",
    "output/database_daily_2026-10-16.db",
    "output/database.db"
]

for db in dbs:
    try:
        conn = sqlite3.connect(db)
        cursor = conn.cursor()
        print(f"\n--- Checking {db} ---")
        if job_id:
            cursor.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE job_id = ?", (job_id,))
            row = cursor.fetchone()
            if row:
                jid, jjson_str, raw_html = row
                print(f"Found by job_id {jid}")
                jdata = json.loads(jjson_str) if jjson_str else {}
                print(f"Title: {jdata.get('title')}")
                desc = jdata.get('description', '')
                print(f"Description length in DB: {len(desc)}")
                print(f"Description preview: {repr(desc[:150])}")
                reviews = jdata.get('reviews', [])
                print(f"Number of reviews in DB: {len(reviews)}")
                for r in reviews:
                    fb = r.get('feedback', '')
                    print(f"  - [{r.get('freelancer')}]: {repr(fb)}")
                
                print(f"Has raw_html: {raw_html is not None}, length: {len(raw_html) if raw_html else 0}")
                if raw_html:
                    with open('scratch/sample_job_raw.html', 'w', encoding='utf-8') as f:
                        f.write(raw_html)
                    print("Saved raw_html to scratch/sample_job_raw.html")
            else:
                print(f"Job ID {job_id} not found in {db}")
        conn.close()
    except Exception as e:
        print(f"Error checking {db}: {e}")
