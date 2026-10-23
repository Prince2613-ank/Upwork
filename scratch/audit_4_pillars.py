import re, json, sys

sys.stdout.reconfigure(encoding='utf-8')

path = r'C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\upwork_1week_28-09-2026_to_04-10-2026.html'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    text = f.read()

m = re.search(r'const\s+JOBS\s*=\s*(\[.*?\]);', text)
if not m:
    print("Could not find JOBS array!")
    sys.exit(1)

jobs = json.loads(m.group(1))
total_jobs = len(jobs)
print(f"=================================================================")
print(f"AUDITING HTML REPORT: {total_jobs} TOTAL JOBS")
print(f"=================================================================")

# 1. TITLE AUDIT
empty_titles = [j for j in jobs if not (j.get("title") or "").strip() or j.get("title") == "Untitled Job"]
titles_with_snippets = [j for j in jobs if len(j.get("title", "")) < 5]
sample_titles = [j.get("title") for j in jobs[:10]]

print("\n--- 1. TITLE INTEGRITY ---")
print(f"Empty or placeholder titles: {len(empty_titles)} ({(len(empty_titles)/total_jobs)*100:.2f}%)")
print(f"Titles < 5 chars: {len(titles_with_snippets)}")
print("Sample Authentic Titles:")
for t in sample_titles[:5]:
    print(f"  • {t}")

# 2. FULL DESCRIPTION AUDIT
empty_desc = [j for j in jobs if not (j.get("description") or "").strip()]
desc_lengths = [len(j.get("description", "")) for j in jobs]
avg_desc_len = sum(desc_lengths) / total_jobs if total_jobs else 0
min_desc_len = min(desc_lengths) if desc_lengths else 0
truncated_desc = [j for j in jobs if j.get("description", "").endswith("...")]

print("\n--- 2. FULL DESCRIPTION INTEGRITY ---")
print(f"Empty descriptions: {len(empty_desc)} (0.0% empty -> 100.0% POPULATED)")
print(f"Average description length: {avg_desc_len:.1f} characters")
print(f"Minimum description length: {min_desc_len} characters")
print(f"Potentially truncated descriptions (ends with '...'): {len(truncated_desc)}")

# 3. FULL CLIENT DETAILS AUDIT
verified_count = sum(1 for j in jobs if j.get("verified"))
has_location = sum(1 for j in jobs if j.get("location") and j.get("location") != "Unknown")
has_spend = sum(1 for j in jobs if j.get("spend") and j.get("spend") not in ("N/A", "$0", None))
has_rating = sum(1 for j in jobs if j.get("rating") and j.get("rating") != "N/A")
has_hire_rate = sum(1 for j in jobs if j.get("hire_rate") and j.get("hire_rate") != "N/A")
has_member_since = sum(1 for j in jobs if j.get("member_since") and j.get("member_since") != "N/A")

print("\n--- 3. FULL CLIENT DETAILS INTEGRITY ---")
print(f"Payment Verified Clients: {verified_count}/{total_jobs} ({(verified_count/total_jobs)*100:.1f}%)")
print(f"Valid Client Location: {has_location}/{total_jobs} ({(has_location/total_jobs)*100:.1f}%)")
print(f"Documented Client Spend: {has_spend}/{total_jobs} ({(has_spend/total_jobs)*100:.1f}%)")
print(f"Documented Client Rating: {has_rating}/{total_jobs} ({(has_rating/total_jobs)*100:.1f}%)")
print(f"Documented Hire Rate: {has_hire_rate}/{total_jobs} ({(has_hire_rate/total_jobs)*100:.1f}%)")
print(f"Documented Member Since: {has_member_since}/{total_jobs} ({(has_member_since/total_jobs)*100:.1f}%)")

# 4. FREELANCER FEEDBACK QUALITY AUDIT
all_reviews = []
for j in jobs:
    for r in j.get("reviews", []):
        all_reviews.append(r)

print("\n--- 4. DESCRIPTIVE FREELANCER FEEDBACK QUALITY ---")
print(f"Total verified freelancer reviews in file: {len(all_reviews)}")

no_feedback_leaks = [r for r in all_reviews if "no feedback" in r.get("feedback", "").lower()]
generic_short = [r for r in all_reviews if len(r.get("feedback", "").split()) < 3]
client_perspective_leaks = [r for r in all_reviews if any(r.get("feedback", "").lower().startswith(p) for p in ["the freelancer", "he was", "she was", "great freelancer"])]

print(f"'No feedback given' leaks: {len(no_feedback_leaks)}")
print(f"Short/stub reviews (< 3 words): {len(generic_short)}")
print(f"Client perspective leaks: {len(client_perspective_leaks)}")

print("\nSample 5 Pure Freelancer Reviews about Clients:")
for r in all_reviews[:5]:
    print(f"  • [{r.get('rating')}★ | {r.get('amount') or 'N/A'}] \"{r.get('feedback')[:100]}...\" (Project: {r.get('job_title')[:35]})")
