import re, json

with open('output/logs/collector.log', encoding='utf-8', errors='replace') as f:
    text = f.read()

jobs_map = {}
curr_url = ''
log_max_seq = 0

for l in text.splitlines():
    m_nav = re.search(r'Navigating to (https://www\.upwork\.com/jobs/[^\s]+)', l)
    if m_nav:
        curr_url = m_nav.group(1)
    m = re.search(r"\[(\d+)\] Collected:\s*'([^']+)'\s*\|\s*Client:\s*([^\|]+)\s*\|\s*History:\s*(\d+)", l)
    if m:
        num = int(m.group(1))
        title = m.group(2)
        log_max_seq = max(log_max_seq, num)
        raw_jid = curr_url.split('_~')[-1].rstrip('/') if '_~' in curr_url else f'job-{num}'
        jid = raw_jid.lstrip('~')
        jobs_map[jid] = {'job_title': title, 'job_url': curr_url, 'num': num}

print(f'log_max_seq: {log_max_seq}')
print(f'jobs_map size: {len(jobs_map)}')

# Search for anime animator
results = [(jid, j) for jid, j in jobs_map.items() if 'anime' in j.get('job_title','').lower() and 'animator' in j.get('job_title','').lower()]
print(f'Anime animator matches: {len(results)}')
for jid, j in results:
    print(f"  jid={jid} | seq={j['num']} | title={j['job_title']}")

# Also show all anime-related
results2 = [(jid, j) for jid, j in jobs_map.items() if 'anime' in j.get('job_title','').lower()]
print(f'\nAll anime-related: {len(results2)}')
for jid, j in results2:
    print(f"  {j['job_title']}")
