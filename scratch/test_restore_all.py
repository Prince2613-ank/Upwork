import sqlite3
import json
import re

def extract_nuxt_strings(raw_html: str):
    if not raw_html:
        return []
    m = re.search(r'<script[^>]*id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>', raw_html, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(1).strip())
        return [s for s in data if isinstance(s, str) and len(s) > 20]
    except Exception:
        return []

def restore_feedback_from_raw(fb: str, raw_html: str, nuxt_strings: list = None) -> str:
    if not fb or not raw_html:
        return fb
    
    # Check if ends with ellipsis
    is_truncated = fb.endswith("...") or fb.endswith("…") or fb.endswith("…")
    if not is_truncated:
        return fb
    
    clean_prefix = fb.rstrip(".… ").strip()
    if len(clean_prefix) < 15:
        return fb

    # 1. First priority: Check Nuxt data strings directly
    if nuxt_strings is None:
        nuxt_strings = extract_nuxt_strings(raw_html)
    
    # Try exact prefix match in Nuxt strings
    # We take the first 30 chars of prefix
    search_sub = clean_prefix[:30].strip()
    best_candidate = None
    for s in nuxt_strings:
        if s.startswith(clean_prefix) or (search_sub and search_sub in s and len(s) > len(fb)):
            # Check similarity / prefix overlap
            if s.startswith(clean_prefix[:20]):
                if best_candidate is None or len(s) > len(best_candidate):
                    best_candidate = s

    if best_candidate and len(best_candidate) > len(fb):
        # Clean any trailing garbage
        return best_candidate.strip()

    # 2. Second priority: search from the END of raw_html where scripts live
    # Find all occurrences of prefix in raw_html
    matches = [m.start() for m in re.finditer(re.escape(clean_prefix[:25]), raw_html)]
    # Check from back to front (scripts are usually at bottom)
    for pos in reversed(matches):
        after = raw_html[pos:pos + 4000]
        # Check if inside JSON string
        m_json = re.match(r'^([^"]+)"', after)
        if m_json:
            candidate = m_json.group(1).replace(r'\"', '"').replace(r'\n', '\n').replace(r'\u002F', '/').strip()
            candidate = re.sub(r'\s+(?:more|less)$', '', candidate, flags=re.I).strip()
            if len(candidate) > len(fb) and not candidate.endswith("...") and not candidate.endswith("…"):
                return candidate

    return fb

# Let's test this on database_yesterday.db
conn = sqlite3.connect("output/database_yesterday.db")
c = conn.cursor()
rows = c.execute("SELECT job_id, job_json, raw_html FROM jobs WHERE raw_html IS NOT NULL").fetchall()
conn.close()

print(f"Total jobs with raw_html in database_yesterday.db: {len(rows)}")

total_reviews = 0
truncated_reviews = 0
restored_reviews = 0

sample_restorations = []

for jid, jjson_str, raw_html in rows:
    try:
        jdata = json.loads(jjson_str) if jjson_str else {}
        history = jdata.get("client_recent_history") or []
        nuxt_strings = None
        for h in history:
            fb = h.get("feedback") or ""
            if not fb:
                continue
            total_reviews += 1
            if fb.endswith("...") or fb.endswith("…"):
                truncated_reviews += 1
                if nuxt_strings is None:
                    nuxt_strings = extract_nuxt_strings(raw_html)
                restored = restore_feedback_from_raw(fb, raw_html, nuxt_strings)
                if restored != fb:
                    restored_reviews += 1
                    if len(sample_restorations) < 5:
                        sample_restorations.append({
                            "job_id": jid,
                            "original": fb,
                            "restored": restored
                        })
    except Exception as e:
        pass

print(f"Total reviews checked: {total_reviews}")
print(f"Truncated reviews found: {truncated_reviews}")
print(f"Successfully restored reviews: {restored_reviews} ({(restored_reviews/truncated_reviews*100) if truncated_reviews else 0:.1f}%)")

print("\n--- SAMPLE RESTORATIONS ---")
for idx, s in enumerate(sample_restorations, 1):
    print(f"\n[Sample #{idx}] Job ID: {s['job_id']}")
    print(f"  ORIGINAL ({len(s['original'])} chars): {repr(s['original'])}")
    print(f"  RESTORED ({len(s['restored'])} chars): {repr(s['restored'])}")
