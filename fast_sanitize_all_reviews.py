import sqlite3
import json
import re
import sys
from bs4 import BeautifulSoup

sys.path.insert(0, '.')
from collector.extraction.review_parser import parse_history_item, clean_review_text

def fast_sanitize():
    print("=" * 75)
    print("🚀 FAST BATCH SANITIZATION: Stripping client->freelancer comments across all DBs")
    print("=" * 75)
    
    db_paths = [
        "output/database_today.db",
        "output/database_daily_2026-10-18.db",
        "output/database_daily_2026-10-17.db",
        "output/database_weekend_2026-10-17_to_2026-10-18.db"
    ]
    
    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE raw_html IS NOT NULL").fetchall()
        print(f"\nProcessing {db_path} ({len(rows)} jobs)...")
        
        updates = []
        for jid, jj, raw_html in rows:
            d = json.loads(jj)
            revs = d.get('client_recent_history') or (d.get('client') or {}).get('recent_history') or []
            if not revs:
                continue
                
            # Parse history items strictly from raw_html using updated review_parser
            if 'client-history' in raw_html or 'contract-history' in raw_html or 'extra-jobs-cards' in raw_html or 'recent history' in raw_html.lower():
                soup = BeautifulSoup(raw_html, 'html.parser')
                sec = soup.select_one('[data-test="client-history"], [data-test="contract-history"], .extra-jobs-cards, .client-history, #client-history')
                if not sec:
                    for s in soup.find_all(['section', 'div', 'article']):
                        h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
                        if h and ("recent history" in h.get_text().lower() or "client history" in h.get_text().lower()):
                            sec = s
                            break
                            
                if sec:
                    items = sec.select('div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"]')
                    if items:
                        new_revs = []
                        for it in items:
                            parsed_item = parse_history_item(it)
                            # Guard
                            t_low = (parsed_item.job_title or "").lower()
                            f_low = (parsed_item.feedback or "").lower()
                            if "explore upwork" in t_low or "already have an account" in f_low or "log in" in f_low:
                                continue
                            if parsed_item.job_title or parsed_item.feedback or parsed_item.amount:
                                new_revs.append(parsed_item.model_dump(mode="json"))
                        
                        if new_revs:
                            d['client_recent_history'] = new_revs
                            if 'client' in d and isinstance(d['client'], dict):
                                d['client']['recent_history'] = new_revs
                            updates.append((json.dumps(d, ensure_ascii=False), jid))

        if updates:
            conn.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", updates)
            conn.commit()
            print(f"✓ Updated {len(updates)} jobs with pure freelancer-only reviews in {db_path}!")
        conn.close()

if __name__ == "__main__":
    fast_sanitize()
