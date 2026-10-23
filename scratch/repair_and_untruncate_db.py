import sqlite3
import json
import re
from pathlib import Path

def extract_nuxt_strings(raw_html: str):
    if not raw_html:
        return []
    m = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', raw_html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1).strip())
        return [s for s in data if isinstance(s, str) and len(s) > 15]
    except Exception:
        return []

def restore_full_feedback_from_raw(fb: str, raw_html: str, nuxt_strings: list = None) -> str:
    if not fb or not raw_html:
        return fb
    
    clean_prefix = re.sub(r'[\s.…\u2026]+$', '', fb).strip()
    if len(clean_prefix) < 15:
        return fb

    # Check Nuxt strings first
    if nuxt_strings is None:
        nuxt_strings = extract_nuxt_strings(raw_html)

    search_sub = clean_prefix[:30].strip()
    best_candidate = None
    for s in nuxt_strings:
        if s.startswith(clean_prefix) or (search_sub and search_sub in s and len(s) > len(fb)):
            if s.startswith(clean_prefix[:20]):
                if best_candidate is None or len(s) > len(best_candidate):
                    best_candidate = s

    if best_candidate and len(best_candidate) > len(fb):
        return best_candidate.strip()

    # Search backwards from end of HTML
    matches = [m.start() for m in re.finditer(re.escape(clean_prefix[:25]), raw_html)]
    for pos in reversed(matches):
        after = raw_html[pos:pos + 4000]
        m_json = re.match(r'^([^"]+)"', after)
        if m_json:
            candidate = m_json.group(1).replace(r'\"', '"').replace(r'\n', '\n').replace(r'\u002F', '/').strip()
            candidate = re.sub(r'\s+(?:more|less)$', '', candidate, flags=re.I).strip()
            if len(candidate) > len(fb) and not candidate.endswith("...") and not candidate.endswith("…") and not candidate.endswith("\u2026"):
                return candidate

    return fb

def repair_db(db_path: Path):
    if not db_path.exists():
        print(f"Skipping {db_path} (does not exist)")
        return

    print(f"\n--- REPAIRING DATABASE: {db_path.name} ---")
    conn = sqlite3.connect(str(db_path))
    c = conn.cursor()
    rows = c.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE raw_html IS NOT NULL").fetchall()
    
    updated_count = 0
    total_reviews_restored = 0

    for jid, jstr, raw_html in rows:
        if not jstr or not raw_html:
            continue
        try:
            d = json.loads(jstr)
            hist = d.get("client_recent_history") or []
            if not hist:
                continue

            nuxt_strings = None
            changed = False
            for h in hist:
                orig_fb = h.get("feedback") or ""
                if not orig_fb:
                    continue
                if orig_fb.endswith("...") or orig_fb.endswith("…") or "\u2026" in orig_fb:
                    if nuxt_strings is None:
                        nuxt_strings = extract_nuxt_strings(raw_html)
                    restored = restore_full_feedback_from_raw(orig_fb, raw_html, nuxt_strings)
                    if restored and restored != orig_fb:
                        h["feedback"] = restored
                        h["feedback_full"] = True
                        changed = True
                        total_reviews_restored += 1

            if changed:
                new_jstr = json.dumps(d, ensure_ascii=False)
                c.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (new_jstr, jid))
                updated_count += 1
        except Exception as e:
            print(f"Error on {jid}: {e}")

    conn.commit()
    conn.close()
    print(f"SUCCESS {db_path.name}: Updated {updated_count} jobs, restored {total_reviews_restored} reviews to 100% full text.")

if __name__ == "__main__":
    dbs = [
        Path("output/database_yesterday.db"),
        Path("output/database_daily_2026-10-15.db"),
        Path("output/database_today.db"),
        Path("output/database_daily_2026-10-16.db"),
        Path("output/database.db"),
        Path("output/database_14days.db")
    ]
    for p in dbs:
        repair_db(p)
