import urllib.request
import json
import sys
sys.stdout.reconfigure(encoding='utf-8')

for port, name in [(9222, 'Chrome'), (9223, 'Edge')]:
    try:
        url = f"http://127.0.0.1:{port}/json/list"
        req = urllib.request.urlopen(url, timeout=3)
        tabs = json.loads(req.read().decode())
        page_tabs = [t for t in tabs if t.get('type') == 'page']
        print(f"\n{name} ({port}) current page tabs ({len(page_tabs)}):")
        
        upwork_tabs = [t for t in page_tabs if 'upwork.com' in (t.get('url') or '')]
        other_tabs = [t for t in page_tabs if 'upwork.com' not in (t.get('url') or '')]
        
        # Keep strictly 1 Upwork tab, close any other Upwork tabs
        if len(upwork_tabs) > 1:
            for t in upwork_tabs[1:]:
                tid = t['id']
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{tid}", timeout=3)
                print(f"   [CLOSED DUPLICATE UPWORK TAB] {t.get('title', '')[:35]}")
        
        # In Chrome, if there is an extra blank tab, close it
        for t in other_tabs:
            if t.get('url') in ['about:blank', 'chrome://newtab/', 'edge://newtab/']:
                tid = t['id']
                urllib.request.urlopen(f"http://127.0.0.1:{port}/json/close/{tid}", timeout=3)
                print(f"   [CLOSED BLANK TAB] {t.get('title', '')}")
                
        # Final status
        req2 = urllib.request.urlopen(url, timeout=3)
        tabs2 = json.loads(req2.read().decode())
        final_pages = [t for t in tabs2 if t.get('type') == 'page']
        print(f"{name} ({port}) remaining tabs ({len(final_pages)}):")
        for t in final_pages:
            print(f"   • {t.get('title', '')[:35]} ({t.get('url', '')[:50]})")
    except Exception as e:
        print(f"{name} error: {e}")
