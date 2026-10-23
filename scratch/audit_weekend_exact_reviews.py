import re
import json

with open('output/upwork_weekend_report.html', 'r', encoding='utf-8') as f:
    c = f.read()

idx = c.find('const JOBS = [')
end = c.find(';\nconst headers =', idx)
text = c[idx+len('const JOBS = ['):end]

# parse objects using json.JSONDecoder().raw_decode
decoder = json.JSONDecoder()
pos = 0
jobs = []
while pos < len(text) and len(jobs) < 8:
    # Skip commas, whitespace
    while pos < len(text) and text[pos] in ' \t\r\n,':
        pos += 1
    if pos >= len(text) or text[pos] == ']':
        break
    try:
        obj, end_pos = decoder.raw_decode(text, pos)
        jobs.append(obj)
        pos = end_pos
    except Exception:
        break

print(f"Auditing {len(jobs)} jobs extracted directly from upwork_weekend_report.html:")
for i, j in enumerate(jobs):
    print(f"\nJob #{i+1}: {j.get('title')}")
    print(f"  Location: {j.get('location')} | Rating: {j.get('rating')} | Spend: {j.get('spend')}")
    print(f"  Reviews count in HTML: {j.get('total_reviews')}")
    for k, r in enumerate(j.get('reviews', [])):
        print(f"    [{k+1}] Freelancer: {r.get('freelancer')} | Rating: {r.get('rating')} | Spend: {r.get('amount')}")
        print(f"        Feedback: \"{r.get('feedback')}\"")
