import json, re, sys

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\upwork_1week_28-09-2026_to_04-10-2026.html', 'r', encoding='utf-8', errors='replace') as f:
    text = f.read()

m = re.search(r'const\s+JOBS\s*=\s*(\[.*?\]);', text)
jobs = json.loads(m.group(1))

total_revs = sum(len(j.get('reviews', [])) for j in jobs)
print('FINAL VERIFICATION:')
print(f'Total Jobs: {len(jobs)}')
print(f'Total Pure Freelancer-to-Client Reviews: {total_revs}')

multi_para = sum(1 for j in jobs for r in j.get('reviews', []) if '\n' in r.get('feedback', ''))
print(f'Multi-paragraph reviews (combined text): {multi_para}')

print('\nFirst 3 Pure Reviews:')
count = 0
for j in jobs:
    for r in j.get('reviews', []):
        print(f"  • [{r.get('rating')}★ | {r.get('amount') or 'N/A'}] \"{r.get('feedback')[:110]}...\"")
        count += 1
        if count >= 3:
            break
    if count >= 3:
        break
