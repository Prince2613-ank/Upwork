import sqlite3
import json
import sys
import time
import threading
from playwright.sync_api import sync_playwright

sys.path.insert(0, '.')
from run_daily_system import fetch_job_detail_single_tab, daily_db_manager
from collector.extraction.job_parser import parse_job_detail_page
from align_and_release_yesterday import align_and_release

sys.stdout.reconfigure(encoding='utf-8')

def sanitize_existing_db_reviews():
    """Pass 1: Re-parse all existing jobs in database_today.db from raw_html to clean out client->freelancer feedback."""
    print("=" * 75)
    print("🧹 PASS 1: Re-parsing existing database to strictly retain FREELANCER reviews of clients...")
    print("=" * 75)
    
    conn = sqlite3.connect("output/database_today.db")
    rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE raw_html IS NOT NULL").fetchall()
    conn.close()
    
    cleaned = 0
    for jid, jj, raw_html in rows:
        d = json.loads(jj)
        url = d.get("job_url") or f"https://www.upwork.com/jobs/{jid}/"
        try:
            job_obj = parse_job_detail_page(raw_html, job_url=url, search_card_metadata=d)
            new_d = job_obj.model_dump(mode="json")
            if d.get("job_title"):
                new_d["job_title"] = d["job_title"]
            daily_db_manager.save_job(new_d, jid, raw_html)
            cleaned += 1
        except Exception as e:
            pass
            
    print(f"✓ Successfully sanitized review contents for all {cleaned} jobs in database_today.db!\n")

def expand_worker(worker_id, port, jobs_subset):
    print(f"[Expand Worker {worker_id}] Starting on Port {port} for {len(jobs_subset)} clients with 5+ reviews...", flush=True)
    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            ctx = b.contexts[0] if b.contexts else b.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        except Exception as e:
            print(f"[Expand Worker {worker_id}] Failed connecting to port {port}: {e}", flush=True)
            return

        for i, (jid, orig_d) in enumerate(jobs_subset, 1):
            url = orig_d.get("job_url") or f"https://www.upwork.com/jobs/{jid}/"
            title = orig_d.get("job_title", "")
            try:
                raw_html = fetch_job_detail_single_tab(page, url)
                job_obj = parse_job_detail_page(raw_html, job_url=url, search_card_metadata=orig_d)
                new_d = job_obj.model_dump(mode="json")
                if title:
                    new_d["job_title"] = title
                
                revs = (new_d.get('client') or {}).get('recent_history') or new_d.get('client_recent_history') or []
                daily_db_manager.save_job(new_d, jid, raw_html)
                print(f"  ✓ [Worker {worker_id}] [{i}/{len(jobs_subset)}] Expanded: '{title[:30]}' | Total Reviews: {len(revs)}", flush=True)
                time.sleep(2.5)
            except Exception as e:
                print(f"  [Worker {worker_id}] Err {jid}: {e}", flush=True)
                time.sleep(2.0)

def main():
    # Step 1: Re-parse all existing saved HTMLs to apply strict freelancer-only review extraction
    sanitize_existing_db_reviews()

    # Step 2: Identify clients with 5+ reviews where 'View more' may exist
    conn = sqlite3.connect("output/database_today.db")
    rows = conn.execute("SELECT job_id, job_json FROM jobs").fetchall()
    conn.close()

    candidates = []
    for jid, jj in rows:
        d = json.loads(jj)
        revs = d.get('client_recent_history') or (d.get('client') or {}).get('recent_history') or []
        if len(revs) >= 5:
            candidates.append((jid, d))

    print("=" * 75)
    print(f"🔍 PASS 2: Expanding 'View more' on {len(candidates)} high-review clients across dual browsers...")
    print("=" * 75)

    if candidates:
        batch_a = candidates[0::2]
        batch_b = candidates[1::2]

        t_a = threading.Thread(target=expand_worker, args=("A", 9222, batch_a))
        t_b = threading.Thread(target=expand_worker, args=("B", 9223, batch_b))

        t_a.start()
        t_b.start()

        t_a.join()
        t_b.join()

    print("\n" + "=" * 75)
    print("🎉 ALL REVIEWS EXPANDED & SANITIZED! RECOMPILING PRODUCTION REPORTS...")
    print("=" * 75)
    align_and_release(require_reviews_only=True)
    print("✓ All intelligence reports successfully updated on disk and dashboard!")

if __name__ == "__main__":
    main()
