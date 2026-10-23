import sqlite3
import json
import re
import sys

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_daily_2026-10-20.db")
row = conn.execute("SELECT raw_html FROM jobs WHERE job_id LIKE '%022112658363064905128%'").fetchone()
conn.close()

html = row[0]
nuxt_match = re.search(r'<script[^>]*__NUXT_DATA__[^>]*>(.*?)</script>', html, re.DOTALL)
if not nuxt_match:
    print("No __NUXT_DATA__ found")
    sys.exit(0)

try:
    nuxt_data = json.loads(nuxt_match.group(1))
    print(f"Nuxt data parsed! Total elements: {len(nuxt_data)}")
    
    # Search for contracts, feedback, reviews, history in nuxt_data
    # Print string elements that contain contract titles or feedback
    strings = [x for x in nuxt_data if isinstance(x, str)]
    print(f"Total string tokens in Nuxt: {len(strings)}")
    
    # Check for known titles
    for s in strings:
        if any(kw in s.lower() for kw in ["backflow", "zoho", "graphic designer", "data collection", "finance specialist"]):
            print("Found contract title in Nuxt:", s)

    # Search for any other job titles or feedback comments
    feedback_candidates = [s for s in strings if len(s) > 25 and not s.startswith("http") and not "<" in s]
    print(f"\nFeedback-like strings ({len(feedback_candidates)}):")
    for fb in feedback_candidates:
        print("  ->", fb)

except Exception as e:
    print("Error parsing Nuxt data:", e)
