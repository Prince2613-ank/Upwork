import re
import sys
from pathlib import Path

# Force UTF-8 output
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

def extract_search_urls(log_path):
    urls = []
    p = Path(log_path)
    if not p.exists():
        return urls
    with open(p, 'r', encoding='utf-8', errors='replace') as f:
        for line in f:
            if 'Fetching Search Page' in line:
                m = re.search(r'Fetching Search Page \d+ \((https://www\.upwork\.com/nx/search/jobs\?[^\)]+)\)', line)
                if m:
                    urls.append(m.group(1))
    return urls

s1_urls = extract_search_urls('C:/Users/princ/.gemini/antigravity-ide/brain/30998f6c-795f-4202-9dd7-7e906fc43a62/.system_generated/tasks/task-6679.log')
s2_urls = extract_search_urls('C:/Users/princ/.gemini/antigravity-ide/brain/30998f6c-795f-4202-9dd7-7e906fc43a62/.system_generated/tasks/task-6656.log')

print("=== SEARCH URL & FILTER VERIFICATION ===")
print(f"Scraper 1 (Port 9222) total search page navigations: {len(s1_urls)}")
if s1_urls:
    print("Latest URL used by Scraper 1:")
    print(" ", s1_urls[-1])

print()
print(f"Scraper 2 (Port 9223) total search page navigations: {len(s2_urls)}")
if s2_urls:
    print("Latest URL used by Scraper 2:")
    print(" ", s2_urls[-1])

expected_filters = [
    ("payment_verified=1", "Payment Verified filter"),
    ("per_page=50", "Per page 50 jobs"),
    ("sort=recency", "Sort by recency"),
    ("location=Europe", "Europe in location list"),
    ("United%20States", "United States in location list"),
    ("United%20Kingdom", "United Kingdom in location list"),
    ("Australia%20and%20New%20Zealand", "Australia and New Zealand in location list"),
    ("Canada", "Canada in location list"),
    ("India", "India in location list"),
]

for name, u in [("Scraper 1 (Port 9222)", s1_urls[-1] if s1_urls else ""), ("Scraper 2 (Port 9223)", s2_urls[-1] if s2_urls else "")]:
    print(f"\n--- Checking {name} ---")
    all_matched = True
    for key, desc in expected_filters:
        ok = key in u
        print(f"  [{'✓' if ok else '✗'}] {desc}: {ok}")
        if not ok:
            all_matched = False
    print(f"Result for {name}: {'100% COMPLETE WITH ALL FILTERS' if all_matched else 'MISSING FILTERS'}")
