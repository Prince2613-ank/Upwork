import re
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

def clean_feedback(fb: str, fl_name: str = "") -> str:
    if not fb:
        return "No feedback given"
    
    # Split on newlines (which separated freelancer->client and client->freelancer)
    lines = [l.strip() for l in fb.split('\n') if l.strip()]
    cleaned_lines = []
    
    # Client reviewing freelancer indicators
    fl_first = (fl_name or "").split()[0].lower() if fl_name else ""
    
    for l in lines:
        l_low = l.lower()
        if (
            l_low.startswith("to freelancer:")
            or l_low.startswith("client:")
            or "feedback to freelancer" in l_low
            or (fl_first and len(fl_first) >= 3 and (l_low.startswith(fl_first) or f"{fl_first} was" in l_low or f"{fl_first} is" in l_low or f"working with {fl_first}" in l_low))
            or any(kw in l_low for kw in [
                "she was", "he was", "she is", "he is", "she delivered", "he delivered",
                "she completed", "he completed", "her work", "his work", "did a great job",
                "did an excellent job", "did good job", "would hire again", "will hire again",
                "would hire him", "would hire her", "will hire him", "will hire her",
                "recommend her", "recommend him", "excellent 3d architect", "very nice work i liked"
            ])
        ):
            continue
        cleaned_lines.append(l)
        
    if not cleaned_lines:
        first_line = lines[0]
        cleaned_lines.append(first_line)
        
    res = cleaned_lines[0]
    # Strip UI truncation artifacts
    res = re.sub(r'\s+(?:more|less)\s*$', '', res, flags=re.IGNORECASE)
    res = re.sub(r'\s*[\u2026\.]+\s*$', '', res).strip()
    return res or "No feedback given"

def process_html_file(file_path):
    p = Path(file_path)
    if not p.exists():
        return
        
    print(f"\nProcessing {p.name}...")
    content = p.read_text(encoding='utf-8')
    
    start_tag = 'const JOBS = ['
    idx = content.find(start_tag)
    if idx == -1:
        print("  JOBS array not found!")
        return
        
    end_tag = ';\nconst headers ='
    end = content.find(end_tag, idx)
    if end == -1:
        end_tag = ';\nconst'
        end = content.find(end_tag, idx)
        
    raw_jobs_str = content[idx + len(start_tag) - 1:end].strip()
    
    try:
        jobs = json.loads(raw_jobs_str)
    except Exception as e:
        decoder = json.JSONDecoder()
        jobs, _ = decoder.raw_decode(raw_jobs_str)
        
    if not isinstance(jobs, list):
        print(f"  Unexpected jobs type: {type(jobs)}")
        return
        
    print(f"  Parsed {len(jobs)} jobs. Cleaning reviews to strictly FREELANCER ONLY...")
    cleaned_reviews_count = 0
    for j in jobs:
        revs = j.get('reviews') or []
        for r in revs:
            old_fb = r.get('feedback', '')
            fl_name = r.get('freelancer', '')
            new_fb = clean_feedback(old_fb, fl_name)
            if old_fb != new_fb:
                r['feedback'] = new_fb
                cleaned_reviews_count += 1
                
    new_jobs_json = json.dumps(jobs, ensure_ascii=False)
    new_content = content[:idx + len('const JOBS = ')] + new_jobs_json + content[end:]
    p.write_text(new_content, encoding='utf-8')
    print(f"✓ Cleaned {cleaned_reviews_count} reviews in {p.name}!")

def main():
    reports = [
        "output/upwork_weekend_report.html",
        "upwork_weekend_report.html",
        "output/upwork_today_report.html",
        "output/upwork_yesterday_report.html",
        "output/upwork_saturday_report.html"
    ]
    for r in reports:
        process_html_file(r)

if __name__ == "__main__":
    main()
