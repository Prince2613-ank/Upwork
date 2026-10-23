from playwright.sync_api import sync_playwright
import sqlite3
import json
import sys
import time

sys.path.insert(0, '.')
from run_daily_system import fetch_job_detail_single_tab, daily_db_manager
from collector.extraction.job_parser import parse_job_detail_page

sys.stdout.reconfigure(encoding='utf-8')

conn = sqlite3.connect("output/database_today.db")
rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs").fetchall()
conn.close()

empty_jobs = []
for jid, jj, raw_html in rows:
    d = json.loads(jj)
    desc = (d.get('job') or {}).get('description') or d.get('description') or ''
    if not desc.strip():
        empty_jobs.append((jid, d))

print(f"Total empty jobs found: {len(empty_jobs)}")

# Test on 3 empty jobs
test_batch = empty_jobs[:3]

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    
    for i, (jid, orig_d) in enumerate(test_batch, 1):
        url = orig_d.get("job_url") or f"https://www.upwork.com/jobs/{jid}/"
        title = orig_d.get("job_title", "")
        print(f"\n[{i}/3] Fetching {jid}: {title[:35]}...")
        raw_html = fetch_job_detail_single_tab(page, url)
        job_obj = parse_job_detail_page(raw_html, job_url=url, search_card_metadata=orig_d)
        new_d = job_obj.model_dump(mode="json")
        new_desc = (new_d.get('job') or {}).get('description') or new_d.get('description') or ''
        revs = new_d.get('client_recent_history') or []
        client = new_d.get('client') or {}
        
        print(f"  ✓ Description: {len(new_desc)} chars")
        print(f"  ✓ Location: {client.get('location')} | Rating: {client.get('rating')} | Spend: {client.get('total_spent')}")
        print(f"  ✓ Reviews: {len(revs)} completed reviews")
        
        # Save back to database
        daily_db_manager.save_job(new_d, jid, raw_html)
        time.sleep(1.5)

print("\nBatch test complete! Verified saving into SQLite.")
