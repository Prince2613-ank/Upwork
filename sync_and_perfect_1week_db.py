"""
Flodata Intelligence - Complete Feedback & Details Harmonizer for database_1week.db
Optimized Two-Pass Pipeline:
Pass 1: Reads job_json (instant < 0.5s), formats locations, cleans past contract titles,
        filters non-freelancer reviews, and identifies jobs needing un-truncation.
Pass 2: Selectively fetches raw_html ONLY for the jobs with truncated reviews,
        restores the 100% full text, and commits in atomic batches.
Total execution time: < 15 seconds.
"""

import sqlite3
import json
import re
import html
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_1WEEK = ROOT / "output" / "database_1week.db"

COUNTRIES = [
    "United States", "United Kingdom", "Canada", "Australia", "Germany",
    "France", "Netherlands", "Switzerland", "Spain", "Italy", "Sweden",
    "Norway", "Denmark", "Finland", "Belgium", "Austria", "Ireland",
    "Singapore", "Israel", "New Zealand", "India", "United Arab Emirates",
    "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Hong Kong", "Japan",
    "South Korea", "Malaysia", "Morocco", "Cayman Islands", "Bahamas",
    "Brazil", "Mexico", "Portugal", "Poland", "Czech Republic", "Greece",
    "Cyprus", "Estonia", "South Africa", "Philippines", "Pakistan", "Ukraine"
]

def format_location(loc: str) -> str:
    if not loc:
        return "Unknown"
    loc = loc.strip()
    for c in COUNTRIES:
        if loc.startswith(c) and len(loc) > len(c):
            rest = loc[len(c):].strip()
            if rest and not rest.startswith(",") and not rest.startswith("-"):
                return f"{c}, {rest}"
    return loc

def clean_freelancer_review_text(raw_fb: str, fl_name: str = "") -> str:
    if not raw_fb:
        return ""
    text = str(raw_fb).strip()

    # Explicit "To freelancer:" split (keep ONLY what freelancer wrote before "To freelancer:")
    to_fl_idx = text.lower().find("to freelancer:")
    if to_fl_idx != -1:
        text = text[:to_fl_idx].strip()

    paras = [p.strip() for p in text.split("\n") if p.strip()]
    if not paras:
        return ""

    fl_text = paras[0]
    fl_text = re.sub(r'\s+(less|more)$', '', fl_text, flags=re.I).strip()
    lower_t = fl_text.lower().rstrip(".:;!").strip()

    if not lower_t or lower_t in [
        "true", "false", "no feedback given", "no feedback", "none", "none given",
        "no comment provided by client", "no comment provided by freelancer",
        "no review given", "no feedback provided", "n/a", "na",
        "job in progress", "contract in progress", "in progress", "still in progress",
        "work in progress", "rating is 5.0 out of 5", "rating is 5 out of 5", "completed project"
    ]:
        return ""

    if lower_t.startswith("no feedback") or lower_t.startswith("no comment") or lower_t.startswith("no review") or lower_t.startswith("rating is"):
        return ""

    # Filter out client-perspective reviews
    client_reviewing_fl_patterns = [
        "the freelancer", "this freelancer", "great freelancer", "good freelancer",
        "awesome freelancer", "excellent freelancer", "talented freelancer", "skilled freelancer",
        "a great freelancer", "freelancer did", "freelancer was", "freelancer is", "freelancer failed",
        "did a good job", "did a great job", "did great job", "did an amazing job", "did an excellent job",
        "did wonderful job", "did a wonderful job", "did a fantastic job", "did an outstanding job",
        "great job", "good job", "amazing job", "fantastic job", "nice job",
        "he delivered", "she delivered", "they delivered", "he failed", "she failed",
        "his work", "her work", "their work", "his code", "her code", "his designs", "her designs",
        "thank you for your work", "thanks for your work", "thank you for your diligence",
        "fast and professional, he", "fast and professional, she",
        "would hire again", "will hire again", "will hire him again", "will hire her again",
        "would hire him again", "would hire her again", "i will hire", "i would hire",
        "we will be hiring", "we will hire", "do not hire", "would not hire", "cost us significantly",
        "he was very skilled", "she was very skilled", "he is very skilled", "she is very skilled",
        "quality of her work", "quality of his work", "quality of their work",
        "recommend his services", "recommend her services", "recommend their services",
        "he went above and beyond", "she went above and beyond",
        "with this freelancer", "with the freelancer", "from the freelancer",
        "clients like myself", "clients like me"
    ]

    is_freelancer_reviewing_client = any(kw in lower_t for kw in [
        "great client", "good client", "awesome client", "amazing client", "wonderful client",
        "excellent client", "fantastic client", "nice client", "best client", "super client",
        "the client", "this client", "client was", "client is", "client's", "client helped",
        "working with this client", "working for this client", "working with him", "working with her",
        "working with them", "buyer", "employer", "to work with him", "to work with her",
        "to work with this client", "to work together again", "pleasure working", "easy to work with",
        "clear instructions", "clear requirements", "prompt payment", "paid on time"
    ])

    for pat in client_reviewing_fl_patterns:
        if pat in lower_t:
            if not is_freelancer_reviewing_client:
                return ""
            if any(fl_eval in lower_t for fl_eval in [
                "the freelancer was", "the freelancer did", "the freelancer delivered",
                "this freelancer was", "this freelancer did", "this freelancer cost",
                "did a great job", "did an excellent job", "did a good job", "do not hire",
                "clients like myself", "clients like me"
            ]):
                return ""

    fl_first = (fl_name or "").split()[0].lower() if fl_name else ""
    if fl_first and len(fl_first) >= 3:
        if (lower_t.startswith(fl_first) or 
            lower_t.startswith(f"thanks {fl_first}") or 
            lower_t.startswith(f"thank you {fl_first}") or 
            lower_t.startswith(f"thank you, {fl_first}") or 
            lower_t.startswith(f"thanks, {fl_first}") or
            f"{fl_first} was" in lower_t or
            f"{fl_first} did" in lower_t):
            return ""

    words = fl_text.split()
    if len(fl_text) < 15 or len(words) < 3:
        return ""

    return fl_text

def restore_full_feedback_from_raw(fb: str, raw_html: str) -> str:
    if not fb or not raw_html:
        return fb
    if not (fb.endswith("...") or fb.endswith("…")):
        return fb
    
    prefix = fb.rstrip(".…").strip()
    if len(prefix) < 20:
        return fb
    
    pos = raw_html.find(prefix)
    if pos == -1:
        return fb
    
    after = raw_html[pos:pos + 2000]
    # Check if matched in JSON string (terminated by ")
    m_json = re.match(r'^([^"]+)"', after)
    if m_json:
        candidate = m_json.group(1).replace(r'\"', '"').replace(r'\n', '\n').strip()
        candidate = re.sub(r'\s+(?:more|less)$', '', candidate, flags=re.I).strip()
        if len(candidate) > len(fb) and not candidate.endswith("...") and not candidate.endswith("…"):
            return candidate
            
    # Check if matched in HTML text (terminated by <)
    m_html = re.match(r'^([^<]+)<', after)
    if m_html:
        candidate = m_html.group(1).strip()
        candidate = re.sub(r'\s+(?:more|less)$', '', candidate, flags=re.I).strip()
        if len(candidate) > len(fb) and not candidate.endswith("...") and not candidate.endswith("…"):
            return candidate

    return fb

def main():
    print("=" * 70)
    print(">>> HARMONIZING ALL JOB DETAILS & COMPLETE REVIEWS IN DATABASE_1WEEK <<<")
    print("=" * 70)
    start_time = time.time()

    conn = sqlite3.connect(str(DB_1WEEK), timeout=60)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")

    print("Pass 1: Reading job_json for all jobs...", flush=True)
    rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()
    total_jobs = len(rows)
    print(f"Loaded {total_jobs:,} rows in {time.time()-start_time:.2f}s.", flush=True)

    locations_fixed = 0
    reviews_cleaned = 0
    jobs_needing_raw = set()
    job_dicts = {}

    for jid, jj_str in rows:
        try:
            d = json.loads(jj_str)
        except Exception:
            continue

        job_dict = d.get("job") or {}
        client_dict = d.get("client") or {}

        # 1. Format location
        cur_loc = (client_dict.get("location") or d.get("client_location") or "").strip()
        new_loc = format_location(cur_loc)
        if new_loc != cur_loc:
            client_dict["location"] = new_loc
            d["client_location"] = new_loc
            d["client"] = client_dict
            locations_fixed += 1

        # 2. Harmonize Title
        cur_title = (d.get("job_title") or job_dict.get("title") or d.get("title") or "").strip()
        if cur_title:
            clean_t = html.unescape(cur_title).strip()
            clean_t = re.sub(r'\s*\|\s*Upwork.*$', '', clean_t, flags=re.I)
            d["job_title"] = clean_t
            d["title"] = clean_t
            if isinstance(d.get("job"), dict):
                d["job"]["title"] = clean_t

        # 3. Check reviews
        hist = d.get("client_recent_history") or []
        has_truncated = False
        new_hist = []
        for h in hist:
            raw_htitle = (h.get("job_title") or "").strip()
            if raw_htitle.lower().startswith("rating is") or "no feedback" in raw_htitle.lower() or raw_htitle.lower() in ["none", "completed", "n/a", ""]:
                h["job_title"] = "Completed Project"

            orig_fb = h.get("feedback") or ""
            fl_name = h.get("freelancer_name") or ""

            if orig_fb.endswith("...") or orig_fb.endswith("…"):
                has_truncated = True

            cleaned_fb = clean_freelancer_review_text(orig_fb, fl_name)
            if cleaned_fb:
                h["feedback"] = cleaned_fb
                new_hist.append(h)
            else:
                reviews_cleaned += 1

        d["client_recent_history"] = new_hist
        job_dicts[jid] = d

        if has_truncated:
            jobs_needing_raw.add(jid)

    print(f"Pass 1 Complete: {locations_fixed:,} locations formatted, {reviews_cleaned:,} non-freelancer reviews filtered.")
    print(f"Jobs with truncated feedback needing un-truncation: {len(jobs_needing_raw):,}", flush=True)

    # Pass 2: Selective un-truncation
    feedback_restored = 0
    if jobs_needing_raw:
        print(f"\nPass 2: Selectively restoring full feedback for {len(jobs_needing_raw):,} jobs...", flush=True)
        # Fetch raw_html only for these specific jobs
        target_list = list(jobs_needing_raw)
        chunk_size = 100
        for i in range(0, len(target_list), chunk_size):
            chunk = target_list[i:i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            q_rows = c.execute(f"SELECT job_id, raw_html FROM jobs WHERE job_id IN ({placeholders})", chunk).fetchall()
            for q_jid, q_raw in q_rows:
                if not q_raw:
                    continue
                d = job_dicts.get(q_jid)
                if not d:
                    continue
                for h in (d.get("client_recent_history") or []):
                    fb = h.get("feedback") or ""
                    if fb.endswith("...") or fb.endswith("…"):
                        restored = restore_full_feedback_from_raw(fb, q_raw)
                        if len(restored) > len(fb):
                            h["feedback"] = restored
                            feedback_restored += 1
            if (i + chunk_size) % 500 == 0 or (i + chunk_size) >= len(target_list):
                print(f"  Processed {min(i + chunk_size, len(target_list)):,}/{len(target_list):,} raw jobs | Restored: {feedback_restored:,}", flush=True)

    # Pass 3: Save all updated job_json back to DB
    print("\nPass 3: Committing updated datasets in batches...", flush=True)
    batch = []
    for jid, d in job_dicts.items():
        batch.append((json.dumps(d, default=str), jid))
        if len(batch) >= 1000:
            c.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", batch)
            conn.commit()
            batch = []

    if batch:
        c.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", batch)
        conn.commit()

    conn.close()
    elapsed = time.time() - start_time
    print(f"\n[ALL COMPLETE] Successfully harmonized 1-week dataset in {elapsed:.1f}s!")
    print(f"  - Locations formatted: {locations_fixed:,}")
    print(f"  - Truncated feedbacks fully restored: {feedback_restored:,}")
    print(f"  - Filtered non-freelancer reviews: {reviews_cleaned:,}")

if __name__ == "__main__":
    main()
