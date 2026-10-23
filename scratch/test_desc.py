from bs4 import BeautifulSoup
from pathlib import Path
import re

sample_ids = ['022101566074174139612', '022101612749136846211', '022101610711744081116']
for sid in sample_ids:
    p = Path(f'output/raw_html/{sid}.html')
    if not p.exists():
        print(f'{sid} does not exist')
        continue
    html = p.read_text(encoding='utf-8', errors='replace')
    soup = BeautifulSoup(html, 'html.parser')
    
    print(f'=== {sid} (HTML len: {len(html)}) ===')
    selectors = [
        '[data-test="job-description-text"]',
        '[data-test="Description"]',
        '.job-description',
        '.up-line-clamp-expanded',
        '[data-test="job-description"]',
        '[data-qa="job-description"]',
        '.air3-line-clamp',
        'p'
    ]
    for sel in selectors:
        match = soup.select(sel)
        if match:
            txt = match[0].get_text(strip=True)[:100]
            print(f'  Selector {sel} matched {len(match)} elements: {txt}')
            
    # Also let's search where the text of the job description might be
    # Let's search for some text inside the page
    main_sec = soup.select_one('.up-card-section')
    print(f'  up-card-section found: {bool(main_sec)}')
    
    # Check all elements with "description" in class or attribute
    desc_matches = soup.find_all(attrs={"class": re.compile(r"desc", re.I)})
    print(f'  Elements with "desc" in class: {len(desc_matches)}')
    for d in desc_matches[:3]:
        print(f'    Tag: {d.name}, class: {d.get("class")}, text: {d.get_text(strip=True)[:80]}')
