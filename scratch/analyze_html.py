"""
Analyze the saved HTML for history section structure.
"""
import sys
import re
from bs4 import BeautifulSoup

with open('output/diagnosis_job_detail.html', 'r', encoding='utf-8', errors='replace') as f:
    html = f.read()

print(f"HTML size: {len(html):,} chars")
soup = BeautifulSoup(html, 'html.parser')

title = soup.select_one('h1')
print(f"Title: {title.get_text()[:100] if title else 'NOT FOUND'}")

print("\n=== TESTING HISTORY SECTION SELECTORS ===")
selectors = [
    "[data-test='client-history']",
    "[data-test='contract-history']",
    ".client-history",
    "#client-history",
    "[data-cy='client-history']",
    "[data-test='ClientHistory']",
    "[data-ev-label='client_history']",
    "[data-qa='client-history']",
]
for sel in selectors:
    count = len(soup.select(sel))
    status = "FOUND" if count else "NOT FOUND"
    print(f"  {status}: '{sel}': {count}")

print("\n=== SECTION HEADERS CONTAINING 'history' ===")
for tag in soup.find_all(['h1','h2','h3','h4','h5','h6','strong','span','p']):
    txt = tag.get_text().strip()
    if 'history' in txt.lower() and len(txt) < 100:
        parent = tag.parent
        gp = parent.parent if parent else None
        print(f"  TEXT: '{txt[:70]}'")
        print(f"    in <{tag.name}> -> <{parent.name if parent else '?'} class='{parent.get('class','') if parent else '?'}'>")
        if gp:
            print(f"    -> <{gp.name} class='{gp.get('class','')}' data-test='{gp.get('data-test','')}' data-cy='{gp.get('data-cy','')}'>")

print("\n=== TESTING ITEM SELECTORS ===")
item_selectors = [
    'div.item[data-cy="job"]',
    "[data-test='history-item']",
    "[data-test='contract-card']",
    ".up-card-sub-section",
    ".history-item",
    "li.air3-card-list-item",
    "[data-ev-label='contract_history_item']",
    "[data-cy='job']",
    "[data-test='ContractHistoryItem']",
    "[data-qa='contract-item']",
    "section[data-test]",
]
for sel in item_selectors:
    count = len(soup.select(sel))
    if count > 0:
        print(f"  FOUND '{sel}': {count} items")
        el = soup.select(sel)[0]
        print(f"    First item text: {el.get_text()[:100].replace(chr(10), ' ')}")

print("\n=== FIND 'recent history' IN TEXT ===")
all_text = soup.get_text()
idx = all_text.lower().find("client's recent history")
if idx == -1:
    idx = all_text.lower().find("recent history")

if idx > -1:
    print(f"Found at char {idx}")
    print(f"Context: {repr(all_text[max(0,idx-30):idx+200])}")
    
    # Find DOM element
    for el in soup.find_all(string=re.compile(r"recent history", re.I)):
        par = el.parent
        print(f"\nContaining element: <{par.name}> class='{par.get('class','')}' data-test='{par.get('data-test','')}' data-cy='{par.get('data-cy','')}'")
        container = par
        # Go up to find a meaningful container
        for _ in range(5):
            container = container.parent
            if not container:
                break
            children = container.find_all(recursive=False)
            if len(children) >= 2:
                print(f"  Container: <{container.name}> class='{container.get('class','')}' data-test='{container.get('data-test','')}' - {len(children)} direct children")
                # Check if items exist here
                for isel in ['li', 'article', 'div.item', '[data-cy]']:
                    ic = len(container.select(isel))
                    if ic > 1:
                        print(f"    items via '{isel}': {ic}")
                break
else:
    print("NOT FOUND in page text")
    print("Check if page is behind login...")
    login_markers = ['log in', 'sign in', 'create account']
    for m in login_markers:
        if m in all_text[:3000].lower():
            print(f"  WARNING: '{m}' found near top!")

print("\n=== PAGE TEXT PREVIEW (first 800 chars) ===")
print(all_text[:800])

print("\n\n=== RUNNING OUR PARSER ===")
sys.path.insert(0, '.')
from collector.extraction.review_parser import parse_client_history
results = parse_client_history(html)
print(f"Our parser found: {len(results)} history items")
for r in results[:10]:
    print(f"  - job_title='{r.job_title[:40]}' | amount={r.amount} | date={r.date} | feedback={r.feedback[:50] if r.feedback else 'N/A'}")
