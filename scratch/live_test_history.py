"""
Live test: Navigate to a job, wait for history to load, then parse.
This diagnoses whether our page_manager fixes work and shows the real HTML structure.
"""
import asyncio
import json
import sys
import time
import urllib.request

TARGET_URL = "https://www.upwork.com/jobs/Dutch-native-speaker-needed-verify-7000-words-machine-translation-from-_~022104206520691535224/"
CDP_PORT = 9223

async def main():
    import websockets
    
    # Get tab list
    with urllib.request.urlopen(f"http://localhost:{CDP_PORT}/json") as r:
        tabs = json.loads(r.read())
    
    target = next((t for t in tabs if t.get('type') == 'page'), None)
    if not target:
        print("No page tab found")
        return
    
    print(f"Using tab: {target.get('url','')[:80]}")
    ws_url = target['webSocketDebuggerUrl']
    
    async with websockets.connect(ws_url, max_size=200*1024*1024) as ws:
        msg_id = [0]
        
        async def send_recv(method, params=None):
            msg_id[0] += 1
            mid = msg_id[0]
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                resp = json.loads(await ws.recv())
                if resp.get('id') == mid:
                    return resp
        
        async def eval_js(expr):
            r = await send_recv("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get('result', {}).get('result', {}).get('value')
        
        # Navigate to job
        print(f"Navigating to: {TARGET_URL}")
        await send_recv("Page.navigate", {"url": TARGET_URL})
        
        # Wait for page to load
        print("Waiting for page load...")
        for i in range(15):
            await asyncio.sleep(1)
            state = await eval_js("document.readyState")
            print(f"  readyState ({i+1}s): {state}")
            if state == 'complete':
                break
        
        # Wait extra for React/AJAX history to load
        print("Waiting for history section (up to 15s)...")
        history_found = False
        for i in range(30):
            await asyncio.sleep(0.5)
            found = await eval_js("""
                (() => {
                    const text = document.body ? document.body.innerText : '';
                    return text.toLowerCase().includes("client's recent history") || 
                           text.toLowerCase().includes("recent history");
                })()
            """)
            if found:
                print(f"  History section appeared after {(i+1)*0.5:.1f}s!")
                history_found = True
                break
        
        if not history_found:
            print("  History section NOT found after 15s")
        
        # Now try scrolling to trigger lazy loading
        print("Scrolling to trigger lazy loads...")
        for scroll_pct in [0.3, 0.6, 0.85, 1.0]:
            await eval_js(f"window.scrollTo(0, document.body.scrollHeight * {scroll_pct})")
            await asyncio.sleep(0.5)
        
        await asyncio.sleep(1.5)
        
        # Check again
        found = await eval_js("""
            (() => {
                const text = document.body ? document.body.innerText : '';
                return text.toLowerCase().includes("client's recent history") || 
                       text.toLowerCase().includes("recent history");
            })()
        """)
        print(f"History section present after scroll: {found}")
        
        # Click "Jobs in progress" toggle
        print("Clicking 'Jobs in progress' toggle...")
        clicked = await eval_js("""
            (() => {
                const candidates = [
                    document.querySelector('[data-cy="jobs-in-progress-button"]'),
                    document.querySelector('[data-test="jobs-in-progress-toggle"]'),
                    ...Array.from(document.querySelectorAll('button')).filter(
                        b => (b.innerText || '').toLowerCase().includes('jobs in progress')
                    )
                ];
                for (const btn of candidates) {
                    if (btn) { btn.click(); return true; }
                }
                return false;
            })()
        """)
        print(f"  Jobs-in-progress clicked: {clicked}")
        if clicked:
            await asyncio.sleep(1.0)
        
        # Click "View more" links
        print("Clicking 'View more' links...")
        total_clicks = 0
        for i in range(30):
            clicked = await eval_js("""
                (() => {
                    const allLinks = Array.from(document.querySelectorAll('a, button'));
                    const target = allLinks.find(el => {
                        const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                        return txt.startsWith('view more') || txt.startsWith('show more') ||
                               txt.startsWith('load more') || txt === 'view all';
                    });
                    if (target) { target.click(); return true; }
                    return false;
                })()
            """)
            if not clicked:
                break
            total_clicks += 1
            await asyncio.sleep(0.5)
        
        print(f"  Clicked 'View more' {total_clicks}x")
        await asyncio.sleep(1.5)
        
        # Get final HTML
        html = await eval_js("document.documentElement.outerHTML")
        print(f"\nFinal HTML: {len(html):,} chars")
        
        with open('output/diagnosis_job_final.html', 'w', encoding='utf-8') as f:
            f.write(html)
        print("Saved to output/diagnosis_job_final.html")
        
        # Extract history items via JS (most reliable method)
        print("\nExtracting history via JS...")
        history_js = """
        (() => {
            // Find the 'Client's recent history' section
            const allElements = Array.from(document.querySelectorAll('*'));
            let historySection = null;
            
            // Find by text content
            for (const el of allElements) {
                if (el.children.length === 0) continue; // Skip leaf nodes
                const directText = Array.from(el.childNodes)
                    .filter(n => n.nodeType === 3)
                    .map(n => n.textContent.trim())
                    .join('');
                const fullText = el.innerText || '';
                if (fullText.toLowerCase().includes("client's recent history") && el.tagName !== 'HTML' && el.tagName !== 'BODY') {
                    historySection = el;
                    break;
                }
            }
            
            if (!historySection) {
                return {found: false, sectionTag: null, text_preview: (document.body.innerText || '').substring(0, 200)};
            }
            
            // Get all text lines for analysis
            const lines = (historySection.innerText || '').split('\\n').filter(l => l.trim());
            
            return {
                found: true,
                sectionTag: historySection.tagName,
                sectionClass: historySection.className,
                sectionDataTest: historySection.getAttribute('data-test'),
                sectionDataCy: historySection.getAttribute('data-cy'),
                lineCount: lines.length,
                preview: lines.slice(0, 30).join(' | '),
                childCount: historySection.children.length,
                innerHTML_preview: (historySection.innerHTML || '').substring(0, 500)
            };
        })()
        """
        result = await eval_js(history_js)
        print(f"JS result: {json.dumps(result, indent=2)}")


asyncio.run(main())
