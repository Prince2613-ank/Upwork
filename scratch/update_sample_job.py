from playwright.sync_api import sync_playwright
import sys
sys.path.insert(0, '.')
from collector.extraction.job_parser import parse_job_detail_page
from run_daily_system import daily_db_manager
import sqlite3
import json

sys.stdout.reconfigure(encoding='utf-8')

with sync_playwright() as p:
    b = p.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = b.contexts[0]
    for page in ctx.pages:
        if "022111270348951686753" in (page.url or ""):
            print("Found job tab in Chrome!")
            c = page.content()
            job_obj = parse_job_detail_page(c, job_url=page.url)
            d = job_obj.model_dump(mode="json")
            jid = d["job_id"]
            print("Parsed title:", d.get("job_title"))
            print("Parsed desc len:", len((d.get("job") or {}).get("description") or ""))
            print("Parsed client:", d.get("client"))
            print("Parsed history count:", len(d.get("client_recent_history") or []))
            
            # Save into database_today.db and database_yesterday.db and database_weekend...
            daily_db_manager.save_job(d, jid, c)
            print("Successfully saved into SQLite via daily_db_manager!")

conn = sqlite3.connect("output/database_today.db")
row = conn.execute("SELECT job_json FROM jobs WHERE job_id LIKE '%022111270348951686753%'").fetchone()
conn.close()
saved_d = json.loads(row[0])
print("\n--- Verified from database_today.db ---")
print("Desc len:", len((saved_d.get("job") or {}).get("description") or ""))
print("Client:", saved_d.get("client"))
print("History count:", len(saved_d.get("client_recent_history") or []))
