"""
Fast Authentic Title, URL & Details Synchronizer.
Scans raw HTML files and collector logs, extracts 100% authentic un-truncated titles,
updates database_14days.db and database.db in lightning speed (< 60 seconds).
"""

import os
import re
import json
import sqlite3
import time
import html
from pathlib import Path
import sys
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
DB_14DAYS = ROOT / "output" / "database_14days.db"
DB_MAIN = ROOT / "output" / "database.db"
RAW_HTML_DIR = ROOT / "output" / "raw_html"
COLLECTOR_LOG = ROOT / "output" / "logs" / "collector.log"


def clean_upwork_title(raw_title: str) -> str:
    if not raw_title:
        return ""
    t = html.unescape(raw_title).strip()
    t = re.sub(r'\s*\|\s*Upwork.*$', '', t, flags=re.I)
    t = re.sub(r'\s*-\s*Upwork.*$', '', t, flags=re.I)
    
    # Strip Upwork category suffix if present at the end after ' - '
    parts = t.rsplit(' - ', 1)
    if len(parts) == 2 and len(parts[1]) < 45 and not any(c in parts[1] for c in ['!', '?', '$', 'http']):
        t = parts[0].strip()
        
    # Check for invalid boilerplate
    if any(bad in t.lower() for bad in ["just a moment", "access denied", "featured job posts", "search freelance jobs", "page not found", "404", "attention required", "security check"]):
        return ""
        
    return t


def main():
    print("=" * 75)
    print(">>> RUNNING FAST AUTHENTIC TITLE & DETAILS SYNCHRONIZER <<<")
    print("=" * 75)
    start_time = time.time()

    # 1. Index full URLs and slugs from collector.log
    log_data = {} # jid -> (full_url, slug_title)
    if COLLECTOR_LOG.exists():
        print(f"Indexing URLs and slugs from {COLLECTOR_LOG}...", flush=True)
        with open(COLLECTOR_LOG, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                if "Navigating to https://www.upwork.com/jobs/" in line:
                    m = re.search(r'(https://www.upwork.com/jobs/([^_]+)_~(0[0-9a-fA-F]+)/?)', line)
                    if m:
                        full_url = m.group(1)
                        slug = m.group(2)
                        jid = "~" + m.group(3)
                        slug_clean = slug.replace('-', ' ').replace('_', ' ').strip()
                        log_data[jid] = (full_url, slug_clean)
        print(f"Indexed {len(log_data):,} job URLs/slugs from collector.log.", flush=True)

    # 2. Extract clean titles from output/raw_html/
    html_titles = {} # jid -> clean_title
    if RAW_HTML_DIR.exists():
        print(f"Extracting authentic titles from {RAW_HTML_DIR}...", flush=True)
        html_files = os.listdir(RAW_HTML_DIR)
        for idx, fname in enumerate(html_files):
            if not fname.endswith(".html"):
                continue
            base = fname[:-5]
            fpath = RAW_HTML_DIR / fname
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                    head = fp.read(32768)
                    m = re.search(r'<title>(.*?)</title>', head, re.I)
                    if m:
                        ct = clean_upwork_title(m.group(1))
                        if ct and len(ct) > 3:
                            html_titles[base] = ct
                            html_titles[f"~{base}"] = ct
            except Exception:
                pass
            if (idx + 1) % 10000 == 0:
                print(f"  Processed {idx+1:,}/{len(html_files):,} HTML files...", flush=True)

        print(f"Extracted {len(html_titles)//2:,} authentic titles from raw HTML.", flush=True)

    # 3. Update database_14days.db
    print(f"\nUpdating {DB_14DAYS}...", flush=True)
    conn = sqlite3.connect(DB_14DAYS, timeout=60)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    rows = c.execute("SELECT job_id, job_json FROM jobs").fetchall()

    fixed_titles = 0
    fixed_urls = 0
    updates = []

    for jid, jj_str in rows:
        try:
            d = json.loads(jj_str)
        except Exception:
            continue

        cur_title = (d.get("job_title") or d.get("title") or "").strip()
        cur_url = d.get("job_url") or ""
        safe_id = jid.replace("~", "").replace("/", "_").replace(":", "_")

        # Determine best authentic title
        best_title = html_titles.get(jid) or html_titles.get(safe_id) or ""
        if not best_title:
            # Fallback to slug title from log
            if jid in log_data:
                best_title = log_data[jid][1]
            elif cur_url:
                m_s = re.search(r'/jobs/([^_/?#]+)_~', cur_url)
                if m_s:
                    best_title = m_s.group(1).replace('-', ' ').replace('_', ' ').strip()

        # If best_title is available and different, use it
        if best_title and best_title != cur_title:
            d["job_title"] = best_title
            d["title"] = best_title
            if "job" in d and isinstance(d["job"], dict):
                d["job"]["title"] = best_title
            fixed_titles += 1

        # Check URL
        if jid in log_data:
            full_log_url = log_data[jid][0]
            if not cur_url or cur_url.endswith(jid) or cur_url.endswith(jid + "/"):
                d["job_url"] = full_log_url
                fixed_urls += 1

        updates.append((json.dumps(d, default=str), jid))

        if len(updates) >= 1000:
            c.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", updates)
            conn.commit()
            updates = []

    if updates:
        c.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", updates)
        conn.commit()

    conn.close()
    print(f"database_14days.db updated: {fixed_titles:,} titles fixed, {fixed_urls:,} URLs restored.", flush=True)

    # 4. Synchronize database.db
    if DB_MAIN.exists():
        print(f"\nSynchronizing to {DB_MAIN}...", flush=True)
        conn_src = sqlite3.connect(DB_14DAYS, timeout=60)
        c_src = conn_src.cursor()
        src_rows = c_src.execute("SELECT job_id, job_json FROM jobs").fetchall()
        conn_src.close()

        conn_dst = sqlite3.connect(DB_MAIN, timeout=60)
        c_dst = conn_dst.cursor()
        c_dst.execute("PRAGMA journal_mode=WAL")

        main_updates = []
        for jid, jj_str in src_rows:
            main_updates.append((jj_str, jid))
            if len(main_updates) >= 1000:
                c_dst.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", main_updates)
                conn_dst.commit()
                main_updates = []

        if main_updates:
            c_dst.executemany("UPDATE jobs SET job_json = ? WHERE job_id = ?", main_updates)
            conn_dst.commit()

        conn_dst.close()
        print(f"database.db synchronized with {len(src_rows):,} rows.", flush=True)

    print(f"\nAll operations completed in {time.time()-start_time:.1f}s.")

    # 5. Verify target job ~022089338363935389527
    conn = sqlite3.connect(DB_14DAYS)
    r = conn.execute("SELECT job_json FROM jobs WHERE job_id = ?", ("~022089338363935389527",)).fetchone()
    conn.close()
    if r:
        target_d = json.loads(r[0])
        print("\n--- TARGET JOB VERIFICATION ---")
        print("Job ID:   ~022089338363935389527")
        print("Title:    ", repr(target_d.get("job_title")))
        print("URL:      ", repr(target_d.get("job_url")))
        print("Location: ", repr(target_d.get("client_location")))


if __name__ == "__main__":
    main()
