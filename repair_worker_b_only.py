import sqlite3
import json
import sys
import time
from playwright.sync_api import sync_playwright

sys.path.insert(0, '.')
from run_daily_system import fetch_job_detail_single_tab, daily_db_manager
from collector.extraction.job_parser import parse_job_detail_page
from align_and_release_yesterday import align_and_release

sys.stdout.reconfigure(encoding='utf-8')

def get_empty_jobs():
    conn = sqlite3.connect("output/database_today.db")
    rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs").fetchall()
    conn.close()

    empty = []
    for jid, jj, raw_html in rows:
        d = json.loads(jj)
        desc = (d.get('job') or {}).get('description') or d.get('description') or ''
        if not desc.strip():
            empty.append((jid, d))
    return empty

def main():
    print("=" * 75)
    print("🛠️ WORKER B ONLY (Edge Port 9223): Repairing Remaining Empty Jobs")
    print("=" * 75)
    
    empty_jobs = get_empty_jobs()
    total = len(empty_jobs)
    print(f"Worker B: Found {total} remaining empty jobs to backfill...", flush=True)
    
    if total == 0:
        print("All jobs are already fully populated! Recompiling releases...", flush=True)
        align_and_release(require_reviews_only=True)
        return

    with sync_playwright() as p:
        try:
            b = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
            ctx = b.contexts[0] if b.contexts else b.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
        except Exception as e:
            print(f"[Worker B] Failed to connect to Edge port 9223: {e}", flush=True)
            return

        repaired = 0
        for i, (jid, orig_d) in enumerate(empty_jobs, 1):
            url = orig_d.get("job_url") or f"https://www.upwork.com/jobs/{jid}/"
            title = orig_d.get("job_title", "")
            try:
                raw_html = fetch_job_detail_single_tab(page, url)
                job_obj = parse_job_detail_page(raw_html, job_url=url, search_card_metadata=orig_d)
                new_d = job_obj.model_dump(mode="json")
                if title:
                    new_d["job_title"] = title
                
                desc = (new_d.get('job') or {}).get('description') or new_d.get('description') or ''
                revs = (new_d.get('client') or {}).get('recent_history') or new_d.get('client_recent_history') or []
                client = new_d.get('client') or {}
                
                if desc.strip() or len(revs) > 0:
                    daily_db_manager.save_job(new_d, jid, raw_html)
                    repaired += 1
                    loc = client.get('location') or '—'
                    print(f"  ✓ [Worker B] [{i}/{total}] Repaired #{repaired}: '{title[:30]}' | Desc: {len(desc)} chars | Loc: {loc} | Revs: {len(revs)}", flush=True)
                else:
                    print(f"  ⚠️ [Worker B] [{i}/{total}] Notice: Still empty (Cloudflare/login) for {jid}", flush=True)
                
                # Pacing between backfills
                time.sleep(2.5)
            except Exception as e:
                print(f"  [Worker B] Err {jid}: {e}", flush=True)
                time.sleep(2.0)

    print(f"\n🎉 [Worker B] Finished! Total successfully repaired: {repaired}/{total}", flush=True)
    align_and_release(require_reviews_only=True)
    print("✓ All intelligence reports successfully updated on disk and dashboard!")

if __name__ == "__main__":
    main()
