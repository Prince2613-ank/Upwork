import sqlite3
import json
import urllib.parse
from collections import Counter
from pathlib import Path

db_path = Path("output/database_1week.db")

# Exact list from user query
user_url = "https://www.upwork.com/nx/search/jobs?location=Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,United%2520States%2520Virgin%2520Islands&payment_verified=1&per_page=50&sort=recency"

parsed = urllib.parse.urlparse(user_url)
qs = urllib.parse.parse_qs(parsed.query)
raw_locs = qs.get("location", [""])[0]
user_countries = [urllib.parse.unquote(c).strip() for c in raw_locs.split(",")]

print("=== TARGET COUNTRIES FROM USER URL ===")
print(f"Total target locations in user's query: {len(user_countries)}")
for idx, c in enumerate(user_countries, 1):
    print(f"  {idx:2d}. {c}")

conn = sqlite3.connect(f"file:{db_path.resolve().as_posix()}?mode=ro", uri=True)
cur = conn.cursor()

cur.execute("SELECT COUNT(*) FROM jobs")
total_jobs = cur.fetchone()[0]

print(f"\n=== DATABASE 1-WEEK LIVE STATS ===")
print(f"Total jobs currently in database_1week.db: {total_jobs:,}")

# Country distribution analysis
cur.execute("SELECT job_json, saved_at FROM jobs")
rows = cur.fetchall()
conn.close()

country_counts = Counter()
for raw_json, saved_at in rows:
    try:
        data = json.loads(raw_json)
        loc = (data.get("client_location") or (data.get("client") or {}).get("location") or "Unknown").strip()
        matched = False
        for tc in user_countries:
            if tc.lower() in loc.lower():
                country_counts[tc] += 1
                matched = True
                break
        if not matched:
            # Check for abbreviations
            if "usa" in loc.lower() or "united states" in loc.lower():
                country_counts["United States"] += 1
            elif "gbr" in loc.lower() or "united kingdom" in loc.lower() or "uk" in loc.lower():
                country_counts["United Kingdom"] += 1
            elif "can" in loc.lower() or "canada" in loc.lower():
                country_counts["Canada"] += 1
            elif "aus" in loc.lower() or "australia" in loc.lower():
                country_counts["Australia and New Zealand"] += 1
            elif "ind" in loc.lower() or "india" in loc.lower():
                country_counts["India"] += 1
            elif "uae" in loc.lower() or "united arab emirates" in loc.lower():
                country_counts["United Arab Emirates"] += 1
            else:
                country_counts[loc.split()[0] if loc else "Unknown"] += 1
    except Exception:
        pass

print("\n=== JOBS STORED BY COUNTRY IN DATABASE ===")
for c, cnt in country_counts.most_common():
    print(f"  - {c}: {cnt:,} jobs")
