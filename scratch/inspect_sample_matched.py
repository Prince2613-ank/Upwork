import json, re, sys

sys.stdout.reconfigure(encoding='utf-8')

with open(r'C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\upwork_1week_28-09-2026_to_04-10-2026.html', 'r', encoding='utf-8', errors='replace') as f:
    text = f.read()

m = re.search(r'const\s+JOBS\s*=\s*(\[.*?\]);', text)
jobs = json.loads(m.group(1))

count = 0
for j in jobs:
    for r in j.get('reviews', []):
        fb = r.get('feedback', '')
        fb_lower = fb.lower()
        if any(w in fb_lower for w in [
            'did a great job', 'did an amazing job', 'did a wonderful job', 'did an excellent job',
            'delivered exactly what', 'pleasure working with him', 'pleasure working with her',
            'would hire him again', 'would hire her again', 'will hire him again', 'will hire her again',
            'hire him again', 'hire her again', 'he was great', 'she was great', 'he is great', 'she is great',
            'he was fast', 'she was fast', 'he was responsive', 'she was responsive', 'he communicated well',
            'she communicated well', 'his work', 'her work', 'super hard task thank you'
        ]):
            print(f"[{count+1}] FL: '{r.get('freelancer')}'")
            print(f"     \"{fb}\"\n")
            count += 1
            if count >= 10:
                break
    if count >= 10:
        break
