"""
Navigate to the Dutch job page via CDP port 9223 and diagnose history section selectors.
"""
import asyncio
import json
import sys

TARGET_URL = "https://www.upwork.com/jobs/Dutch-native-speaker-needed-verify-7000-words-machine-translation-from-_~022104206520691535224/"
CDP_PORT = 9223

async def get_html_from_cdp(cdp_port: int, url_to_navigate: str = None):
    import websockets
    import urllib.request
    
    # Get tabs
    with urllib.request.urlopen(f"http://localhost:{cdp_port}/json") as r:
        tabs = json.loads(r.read())
    
    print(f"Port {cdp_port} has {len(tabs)} tabs")
    for t in tabs:
        print(f"  [{t.get('type')}] {t.get('url','')[:80]}")
    
    # Find best tab
    target = None
    for t in tabs:
        if t.get('type') == 'page':
            target = t
            break
    
    if not target:
        print("No page tab found")
        return None
    
    ws_url = target['webSocketDebuggerUrl']
    print(f"\nConnecting to: {ws_url[:60]}")
    
    async with websockets.connect(ws_url, max_size=100*1024*1024) as ws:
        msg_id = [0]
        def next_id():
            msg_id[0] += 1
            return msg_id[0]
        
        async def send_recv(method, params=None):
            mid = next_id()
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get('id') == mid:
                    return resp
        
        # Navigate to target URL
        if url_to_navigate:
            current_url_resp = await send_recv("Runtime.evaluate", {
                "expression": "window.location.href",
                "returnByValue": True
            })
            current_url = current_url_resp.get('result', {}).get('result', {}).get('value', '')
            print(f"Current URL: {current_url[:80]}")
            
            if url_to_navigate not in current_url:
                print(f"Navigating to: {url_to_navigate}")
                await send_recv("Page.navigate", {"url": url_to_navigate})
                await asyncio.sleep(6)
                print("Navigation done, waiting for page load...")
                
                # Wait for page to load
                for i in range(10):
                    ready = await send_recv("Runtime.evaluate", {
                        "expression": "document.readyState",
                        "returnByValue": True
                    })
                    state = ready.get('result', {}).get('result', {}).get('value', '')
                    print(f"  readyState: {state}")
                    if state == 'complete':
                        break
                    await asyncio.sleep(1)
        
        # Get HTML
        html_resp = await send_recv("Runtime.evaluate", {
            "expression": "document.documentElement.outerHTML",
            "returnByValue": True
        })
        html = html_resp.get('result', {}).get('result', {}).get('value', '')
        print(f"Got HTML: {len(html):,} chars")
        return html


async def diagnose(html: str):
    from bs4 import BeautifulSoup
    import re
    
    soup = BeautifulSoup(html, 'html.parser')
    
    title = soup.select_one('h1')
    print(f"\nPage title (h1): {title.get_text()[:80] if title else 'NOT FOUND'}")
    
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
        if count:
            print(f"  ✓ '{sel}': {count} found")
        else:
            print(f"  ✗ '{sel}': 0")
    
    print("\n=== SECTION HEADERS CONTAINING 'history' ===")
    for tag in soup.find_all(['h1','h2','h3','h4','h5','h6','strong','span','p']):
        txt = tag.get_text().strip()
        if 'history' in txt.lower() and len(txt) < 80:
            parent = tag.parent
            print(f"  Found: '{txt}' in <{tag.name}> inside <{parent.name} class='{parent.get('class','')}'> data-test='{parent.get('data-test','')}'")
    
    print("\n=== LOOKING FOR CONTRACT ITEMS ===")
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
    ]
    for sel in item_selectors:
        count = len(soup.select(sel))
        if count:
            print(f"  ✓ '{sel}': {count} items")
    
    # Try to find history section by text proximity
    print("\n=== FINDING HISTORY SECTION BY TEXT ===")
    all_text = soup.get_text()
    idx = all_text.lower().find("client's recent history")
    if idx == -1:
        idx = all_text.lower().find("recent history")
    
    if idx > -1:
        print(f"Found 'recent history' at char {idx}")
        context = all_text[max(0,idx-50):idx+300]
        print(f"Context: {repr(context[:300])}")
        
        # Find the DOM element containing this text
        for el in soup.find_all(text=re.compile(r"client.s recent history|recent history", re.I)):
            parent = el.parent
            while parent and parent.name not in ['div', 'section', 'article', 'aside']:
                parent = parent.parent
            if parent:
                print(f"\n  History section element: <{parent.name}>")
                print(f"  Attrs: {dict(parent.attrs)}")
                # Count children
                children = parent.find_all(recursive=False)
                print(f"  Direct children: {len(children)}")
                
                # Go up to find the main container
                grandparent = parent.parent
                if grandparent:
                    print(f"  Parent: <{grandparent.name}> attrs={dict(grandparent.attrs)}")
                    gp_children = grandparent.find_all(recursive=False)
                    print(f"  Parent direct children: {len(gp_children)}")
                    for gc in gp_children[:3]:
                        print(f"    <{gc.name}> class={gc.get('class','')} data-test={gc.get('data-test','')} data-cy={gc.get('data-cy','')}")
                break
    else:
        print("'recent history' NOT FOUND in page text!")
        print("Page may be requiring login or JS render")
        
    # Check if page has login wall
    print("\n=== CHECKING FOR LOGIN/AUTH WALL ===")
    page_lower = all_text[:2000].lower()
    markers = ['log in', 'sign in', 'create account', 'login required', 'you must be logged']
    for m in markers:
        if m in page_lower:
            print(f"  WARNING: '{m}' found near top of page!")
    
    # Show first 500 chars of text
    print(f"\n=== PAGE TEXT PREVIEW (first 600 chars) ===")
    print(all_text[:600])


async def main():
    html = await get_html_from_cdp(CDP_PORT, url_to_navigate=TARGET_URL)
    if not html:
        print("Failed to get HTML")
        return
    
    with open('output/diagnosis_job_detail.html', 'w', encoding='utf-8') as f:
        f.write(html)
    print("HTML saved to output/diagnosis_job_detail.html")
    
    await diagnose(html)
    
    print("\n=== RUNNING OUR PARSER ===")
    sys.path.insert(0, '.')
    from collector.extraction.review_parser import parse_client_history
    results = parse_client_history(html)
    print(f"Our parser found: {len(results)} history items")
    for r in results[:5]:
        print(f"  - '{r.job_title[:40]}' | {r.amount} | {r.date} | {r.feedback[:50] if r.feedback else 'N/A'}")


asyncio.run(main())
