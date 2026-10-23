import re, sys
from pathlib import Path
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf-8')

raw_dir = Path('output/raw_html')
count = 0
for f in raw_dir.glob('*.html'):
    try:
        content = f.read_text(encoding='utf-8', errors='replace')
        if 'air3-truncation-' in content and ('stars' in content.lower() or 'rating is' in content.lower()):
            soup = BeautifulSoup(content, 'html.parser')
            sec = soup.select_one("[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history")
            if sec:
                items = sec.select('div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], .up-card-sub-section, .history-item, li.air3-card-list-item, article')
                for item in items:
                    spans = item.select('span[id^="air3-truncation-"]')
                    if spans:
                        print(f"=== File: {f.name} ===")
                        print("RAW TEXT:")
                        print(item.get_text(separator=' \n ', strip=True)[:400])
                        print("\nALL SPANS:")
                        for idx, sp in enumerate(spans):
                            # Print parent or surrounding text as well
                            parent = sp.parent
                            parent_text = parent.get_text(strip=True) if parent else ""
                            prev = sp.find_previous_sibling()
                            prev_text = prev.get_text(strip=True) if prev else ""
                            print(f"  Span #{idx} (id={sp.get('id')}):")
                            print(f"    Text: {sp.get_text(strip=True)}")
                            print(f"    Prev sibling: {prev_text}")
                            print(f"    Parent tag/classes: {parent.name} {parent.get('class', [])}")
                        print("================================================================")
                        count += 1
                        if count >= 3:
                            sys.exit(0)
    except Exception as e:
        pass
