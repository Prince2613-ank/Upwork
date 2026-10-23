import re, json, sys

sys.stdout.reconfigure(encoding='utf-8')

path = r'C:\Users\princ\.gemini\antigravity-ide\scratch\flodata-upwork-intelligence\upwork_1week_28-09-2026_to_04-10-2026.html'
with open(path, 'r', encoding='utf-8', errors='replace') as f:
    text = f.read()

m = re.search(r'const\s+JOBS\s*=\s*(\[.*?\]);', text)
jobs = json.loads(m.group(1))

total_revs = 0
client_perspective = []
two_paras = []
sample_pure_fl = []

for j in jobs:
    for r in j.get('reviews', []):
        total_revs += 1
        fb = r.get('feedback', '')
        paras = [p.strip() for p in fb.split('\n') if p.strip()]
        if len(paras) > 1:
            two_paras.append((j.get('id'), r))
        
        # Check if text is client talking about freelancer
        fb_lower = fb.lower()
        if any(w in fb_lower for w in [
            'did a great job', 'did an amazing job', 'did a wonderful job', 'did an excellent job',
            'delivered exactly what', 'pleasure working with him', 'pleasure working with her',
            'would hire him again', 'would hire her again', 'will hire him again', 'will hire her again',
            'hire him again', 'hire her again', 'he was great', 'she was great', 'he is great', 'she is great',
            'he was fast', 'she was fast', 'he was responsive', 'she was responsive', 'he communicated well',
            'she communicated well', 'his work', 'her work', 'super hard task thank you'
        ]):
            client_perspective.append((j.get('id'), r))

print(f"Total reviews in HTML: {total_revs}")
print(f"Reviews with multiple paragraphs (likely combined FL + Client): {len(two_paras)} ({len(two_paras)/total_revs*100:.1f}%)")
print(f"Reviews containing Client-perspective phrases: {len(client_perspective)} ({len(client_perspective)/total_revs*100:.1f}%)")

print("\nSample 5 Multi-Paragraph Reviews:")
for jid, r in two_paras[:5]:
    print(f"\n--- Job: {jid} | Freelancer: {r.get('freelancer')} ---")
    print(r.get('feedback'))
