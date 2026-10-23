import re
import json

path = 'output/upwork_weekend_report.html'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

# In upwork_weekend_report.html, find const JOBS = [...]
m = re.search(r'const JOBS\s*=\s*(\[\s*\{.*?\}\s*\]);\s*(?:const|let|var|function|\n\s*const)', content, re.DOTALL)
if not m:
    # Try finding the JOBS array by bracket matching
    start_idx = content.find('const JOBS = [')
    if start_idx != -1:
        # find matching closing bracket
        open_b = 0
        end_idx = -1
        in_str = False
        escape = False
        for i in range(start_idx + len('const JOBS = '), len(content)):
            ch = content[i]
            if escape:
                escape = False
                continue
            if ch == '\\':
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if not in_str:
                if ch == '[':
                    open_b += 1
                elif ch == ']':
                    if open_b == 0:
                        end_idx = i + 1
                        break
                    open_b -= 1
        jobs_json_str = content[start_idx + len('const JOBS = '):end_idx]
        jobs = json.loads(jobs_json_str)
else:
    jobs = json.loads(m.group(1))

print(f"Total jobs in report: {len(jobs)}")

total_reviews = 0
jobs_with_reviews = 0
review_counts_dist = {}
client_pollution_found = 0
sample_reviews = []

for j in jobs:
    revs = j.get('client_reviews_list') or j.get('client_recent_history') or []
    n = len(revs)
    if n > 0:
        jobs_with_reviews += 1
        total_reviews += n
        review_counts_dist[n] = review_counts_dist.get(n, 0) + 1
        
        for r in revs:
            fb = r.get('feedback', '')
            if 'to freelancer:' in fb.lower() or 'feedback to freelancer' in fb.lower():
                client_pollution_found += 1
            if len(sample_reviews) < 5 and fb and fb != 'No feedback given':
                sample_reviews.append((j.get('title') or j.get('job_title'), r.get('job_title'), fb))

print(f"Jobs with reviews: {jobs_with_reviews} / {len(jobs)}")
print(f"Total reviews: {total_reviews}")
print("Distribution of review counts per job:", sorted(review_counts_dist.items()))
print(f"Client->Freelancer pollution ('To freelancer:'): {client_pollution_found} occurrences (0 is ideal)")
print("\nSample reviews in the report:")
for job_t, contract_t, fb in sample_reviews:
    print(f" - Job: '{job_t[:30]}...' | Contract: '{contract_t}'")
    print(f"   Review: \"{fb[:120]}...\"\n")
