import sqlite3
import json
import re
import sys
import time

sys.path.insert(0, '.')
from align_and_release_yesterday import align_and_release

def clean_feedback_string(fb: str) -> str:
    if not fb:
        return "No feedback given"
    
    # Split by newline (where client-to-freelancer review was concatenated)
    lines = [l.strip() for l in fb.split('\n') if l.strip()]
    cleaned_lines = []
    for l in lines:
        l_low = l.lower()
        # Drop client review of freelancer
        if l_low.startswith("to freelancer:") or l_low.startswith("client:") or "feedback to freelancer" in l_low:
            continue
        cleaned_lines.append(l)
        
    if not cleaned_lines:
        return "No feedback given"
        
    # The first line is strictly the freelancer's review of the client
    primary = cleaned_lines[0]
    # Clean any trailing truncation or button text
    primary = re.sub(r'\s+(?:more|less)\s*$', '', primary, flags=re.IGNORECASE)
    primary = re.sub(r'\s*[\u2026\.]+\s*$', '', primary) # strip trailing ellipsis
    return primary.strip() or "No feedback given"

def main():
    print("=" * 75)
    print("⚡ INSTANT REVIEW SANITIZATION & RELEASE")
    print("=" * 75)
    
    db_paths = [
        "output/database_today.db",
        "output/database_daily_2026-10-18.db",
        "output/database_daily_2026-10-17.db",
        "output/database_weekend_2026-10-17_to_2026-10-18.db"
    ]
    
    for db_path in db_paths:
        conn = sqlite3.connect(db_path)
        rows = conn.execute("SELECT job_id, job_json FROM jobs").fetchall()
        
        updates = []
        for jid, jj in rows:
            d = json.loads(jj)
            revs = d.get('client_recent_history') or (d.get('client') or {}).get('recent_history') or []
            if not revs:
                continue
                
            changed = False
            for r in revs:
                old_fb = r.get('feedback', '')
                new_fb = clean_feedback_string(old_fb)
                if old_fb != new_fb:
                    r['feedback'] = new_fb
                    changed = True
                    
            if changed:
                d['client_recent_history'] = revs
                if 'client' in d and isinstance(d['client'], dict):
                    d['client']['recent_history'] = revs
                updates.append((json.dumps(d, ensure_ascii=False), jid))
                
        if updates:
            conn.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", updates)
            conn.commit()
            print(f"✓ Sanitized {len(updates)} jobs in {db_path}", flush=True)
        conn.close()

    print("\n" + "=" * 75)
    print("🚀 COMPILING PRODUCTION REPORTS WITH CLEAN FREELANCER REVIEWS...")
    print("=" * 75)
    align_and_release(require_reviews_only=True)
    print("✓ Done! HTML reports generated successfully.", flush=True)

if __name__ == "__main__":
    main()
