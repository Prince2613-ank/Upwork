import csv, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

with open('output/client_history.csv', 'r', encoding='utf-8-sig', errors='replace') as f:
    reader = csv.DictReader(f)
    samples = []
    for row in reader:
        fb = (row.get('feedback') or '').strip()
        if len(fb) > 40 and not fb.lower().startswith('no feedback') and 'connects' not in fb.lower():
            samples.append((row.get('history_job_title'), row.get('freelancer_name'), fb))
            if len(samples) >= 15:
                break

for i, (ht, fn, fb) in enumerate(samples):
    print(f"[{i+1}] Contract: '{ht}' | Freelancer: '{fn}'")
    print(f"    Feedback: {fb}")
    print()
