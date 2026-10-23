import csv
from bs4 import BeautifulSoup
from pathlib import Path
import re
from collector.extraction.job_parser import extract_full_description

with open('output/jobs.csv', 'r', encoding='utf-8-sig') as f:
    reader = csv.DictReader(f)
    empty_jobs = []
    for r in reader:
        desc = (r.get('job_description') or r.get('description') or '').strip()
        if not desc or desc.lower() == 'none':
            empty_jobs.append(r)

print(f"Total empty jobs in CSV: {len(empty_jobs)}")

html_found = 0
re_extract_current_success = 0
re_extract_improved_success = 0

def improved_extract_description(soup: BeautifulSoup) -> str:
    # 1. Standard Upwork data-test attributes
    selectors = [
        "[data-test='job-description-text']",
        "[data-test='Description']",
        "[data-test='job-description']",
        "[data-qa='job-description']",
        ".job-description",
        ".up-line-clamp-expanded",
        ".description-box",
        ".break-word[data-v-]",
        ".job-description-text",
        "[itemprop='description']",
    ]
    for sel in selectors:
        el = soup.select_one(sel)
        if el:
            txt = el.get_text(separator="\n").strip()
            # Clean up buttons
            txt = re.sub(r'(\.\.\.|\u2026)?\s*(?:more|less)\s*$', '', txt, flags=re.IGNORECASE).strip()
            if len(txt) > 20:
                return txt

    # 2. Look for section or div with class containing description
    for el in soup.find_all(attrs={"class": re.compile(r"description|project-requirements", re.I)}):
        txt = el.get_text(separator="\n").strip()
        if len(txt) > 30 and not any(k in txt.lower() for k in ["fixed-price", "experience level", "hourly"]):
            return txt

    # 3. Fallback to current parser logic
    return extract_full_description(soup)

for j in empty_jobs:
    jid = j.get('job_id', '')
    clean_id = jid.replace('~', '')
    p = Path(f"output/raw_html/{clean_id}.html")
    if not p.exists():
        p = Path(f"output/raw_html/{jid}.html")
    
    if p.exists():
        html_found += 1
        html = p.read_text(encoding="utf-8", errors="replace")
        soup = BeautifulSoup(html, "html.parser")
        
        # Test current
        cur_desc = extract_full_description(soup)
        if cur_desc and len(cur_desc) > 10:
            re_extract_current_success += 1
            
        # Test improved
        imp_desc = improved_extract_description(soup)
        if imp_desc and len(imp_desc) > 10:
            re_extract_improved_success += 1

print(f"HTML files found on disk: {html_found} / {len(empty_jobs)}")
print(f"Recovered with current extract_full_description: {re_extract_current_success}")
print(f"Recovered with improved_extract_description: {re_extract_improved_success}")
