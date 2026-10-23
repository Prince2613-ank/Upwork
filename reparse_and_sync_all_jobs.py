"""
Flodata Analytics - Comprehensive Job Details, Titles & Reviews Synchronizer
Fixes all job title mismatches, restores full authentic titles from raw HTML & slugs,
preserves full descriptions, extracts 10-field client intelligence dossiers,
and compiles all client history contracts (including completed & in-progress contracts).
"""

import os
import re
import json
import sqlite3
import time
from pathlib import Path
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

ROOT = Path(__file__).resolve().parent
DB_14DAYS = ROOT / "output" / "database_14days.db"
DB_MAIN = ROOT / "output" / "database.db"
RAW_HTML_DIR = ROOT / "output" / "raw_html"
COLLECTOR_LOG = ROOT / "output" / "logs" / "collector.log"
CSV_HISTORY = ROOT / "output" / "client_history.csv"


def clean_title(title_tag_text, header_text, slug_text, cur_title):
    """Returns the most authentic, non-generic, un-truncated title."""
    for cand in [header_text, title_tag_text]:
        if cand:
            c = cand.strip()
            # Remove Upwork title tag boilerplate
            c = re.sub(r'\s*\|\s*Upwork.*$', '', c, flags=re.I)
            parts = re.split(r'\s+-\s+(?:Marketing|Design|Development|Writing|Admin|Customer|Sales|Accounting|Legal|Engineering|IT|Web|Mobile|Software|Data|AI|Translation|Upwork)', c, flags=re.I)
            if parts and len(parts[0].strip()) > 3:
                clean_cand = parts[0].strip()
                if not any(bad in clean_cand.lower() for bad in [
                    "featured job posts", "search freelance jobs", "just a moment", 
                    "access denied", "page not found", "404", "attention required",
                    "security check", "cloudflare"
                ]):
                    return clean_cand

    if slug_text and len(slug_text) > 3:
        clean_slug = slug_text.replace('-', ' ').replace('_', ' ').strip()
        if not any(bad in clean_slug.lower() for bad in ["featured job posts", "search freelance jobs"]):
            return clean_slug

    return cur_title or "Untitled Job"


def clean_description(soup):
    """Extracts complete un-truncated description from HTML preserving linebreaks."""
    for sel in [
        "[data-test='job-description-text']",
        "[data-test='Description']",
        "[data-test='job-description']",
        "[data-qa='job-description']",
        "p.multiline-text",
        ".job-details .multiline-text",
        ".job-description",
        ".description-box",
        ".break-word[data-v-]"
    ]:
        el = soup.select_one(sel)
        if el:
            import copy
            el_copy = copy.copy(el)
            for tag in el_copy.find_all(["button", "a", "script", "style"]):
                if re.search(r"^\s*(?:\.\.\.|\u2026)?\s*(?:more|less)\s*$", tag.get_text(), re.I):
                    tag.decompose()
            for br in el_copy.find_all("br"):
                br.replace_with("\n")
            lines = [p.get_text().strip() for p in el_copy.find_all(["p", "div", "li"]) if p.get_text().strip()]
            txt = "\n\n".join(lines) if lines else el_copy.get_text(separator="\n").strip()
            txt = re.sub(r"(\.\.\.|\u2026)?\s*(?:more|less)\s*$", "", txt, flags=re.IGNORECASE).strip()
            if len(txt) > 25:
                return txt
    return ""


def format_location(loc):
    if not loc:
        return "Unknown"
    loc = loc.strip()
    countries = [
        "United States", "United Kingdom", "Canada", "Australia", "Germany",
        "France", "Netherlands", "Switzerland", "Spain", "Italy", "Sweden",
        "Norway", "Denmark", "Finland", "Belgium", "Austria", "Ireland",
        "Singapore", "Israel", "New Zealand", "India", "United Arab Emirates",
        "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Hong Kong", "Japan",
        "South Korea", "Malaysia", "Morocco", "Cayman Islands", "Bahamas"
    ]
    for c in countries:
        if loc.startswith(c) and len(loc) > len(c):
            rest = loc[len(c):].strip()
            if rest and not rest.startswith(",") and not rest.startswith("-"):
                return f"{c}, {rest}"
    return loc


def main():
    print("=" * 75)
    print(">>> STARTING COMPREHENSIVE RE-PARSING & SYNCHRONIZATION <<<")
    print("=" * 75)

    # 1. Index full URLs and slugs from collector.log
    log_urls = {}
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
                        log_urls[jid] = (full_url, slug)
        print(f"Indexed {len(log_urls):,} URLs and slugs from collector.log.", flush=True)

    # 2. Index raw_html directory files
    raw_html_files = {}
    if RAW_HTML_DIR.exists():
        print(f"Indexing raw_html directory {RAW_HTML_DIR}...", flush=True)
        for fname in os.listdir(RAW_HTML_DIR):
            if fname.endswith(".html"):
                base = fname[:-5]
                raw_html_files[base] = fname
                raw_html_files[f"~{base}"] = fname
        print(f"Indexed {len(raw_html_files)//2:,} raw HTML files.", flush=True)

    # Import parsers
    from collector.extraction.client_parser import parse_about_client
    from collector.extraction.review_parser import parse_client_history

    # 3. Process database_14days.db
    print(f"\nProcessing all jobs in {DB_14DAYS}...", flush=True)
    conn = sqlite3.connect(DB_14DAYS, timeout=60)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    rows = c.execute("SELECT job_id, job_json, raw_html FROM jobs").fetchall()
    total_jobs = len(rows)
    print(f"Found {total_jobs:,} total rows in database_14days.db.", flush=True)

    updated_count = 0
    title_fixed_count = 0
    desc_fixed_count = 0
    history_fixed_count = 0
    batch_updates = []

    start_time = time.time()

    for idx, (jid, jj_str, db_raw) in enumerate(rows, 1):
        try:
            d = json.loads(jj_str)
        except Exception:
            d = {}

        cur_title = (d.get("job_title") or d.get("title") or "").strip()
        cur_url = d.get("job_url") or ""
        log_info = log_urls.get(jid)
        log_url = log_info[0] if log_info else ""
        slug_text = log_info[1] if log_info else ""

        if not slug_text and cur_url:
            m_s = re.search(r'/jobs/([^_/?#]+)_~', cur_url)
            if m_s:
                slug_text = m_s.group(1)

        # Get HTML if available
        html_content = db_raw or ""
        safe_id = jid.replace("~", "").replace("/", "_").replace(":", "_")
        if not html_content:
            fname = raw_html_files.get(safe_id) or raw_html_files.get(jid)
            if fname:
                try:
                    fpath = RAW_HTML_DIR / fname
                    with open(fpath, "r", encoding="utf-8", errors="ignore") as fp:
                        html_content = fp.read()
                except Exception:
                    pass

        soup = BeautifulSoup(html_content, "html.parser") if html_content else None

        # A. True Title
        title_tag_text = ""
        header_text = ""
        if soup:
            t_tag = soup.find("title")
            if t_tag:
                title_tag_text = t_tag.get_text().strip()
            h_el = soup.select_one("header h1, header h4, [data-test='job-title'], h4.job-title, h1.job-title, main h4, main h1")
            if h_el:
                header_text = h_el.get_text(strip=True)

        new_title = clean_title(title_tag_text, header_text, slug_text, cur_title)
        if new_title and new_title != cur_title:
            title_fixed_count += 1
            d["job_title"] = new_title
            d["title"] = new_title
            if "job" in d and isinstance(d["job"], dict):
                d["job"]["title"] = new_title

        # B. Full URL
        if log_url and (not cur_url or cur_url.endswith(jid) or cur_url.endswith(jid + "/")):
            d["job_url"] = log_url

        # C. Full Description
        job_dict = d.get("job") or {}
        cur_desc = (job_dict.get("description") or d.get("description") or "").strip()
        if soup:
            html_desc = clean_description(soup)
            if html_desc and len(html_desc) > len(cur_desc):
                d["description"] = html_desc
                if isinstance(d.get("job"), dict):
                    d["job"]["description"] = html_desc
                desc_fixed_count += 1

        # D. Client Intelligence
        client_dict = d.get("client") or {}
        if soup and (not client_dict.get("location") or not client_dict.get("total_spent")):
            cl = parse_about_client(soup)
            if cl.location:
                client_dict["location"] = format_location(cl.location)
                d["client_location"] = client_dict["location"]
            if cl.rating: client_dict["rating"] = cl.rating
            if cl.total_spent: client_dict["total_spent"] = cl.total_spent
            if cl.jobs_posted: client_dict["jobs_posted"] = cl.jobs_posted
            if cl.hire_rate: client_dict["hire_rate"] = cl.hire_rate
            if cl.total_hires: client_dict["total_hires"] = cl.total_hires
            if cl.active_hires: client_dict["active_hires"] = cl.active_hires
            if cl.hours_billed: client_dict["hours_billed"] = cl.hours_billed
            if cl.member_since: client_dict["member_since"] = cl.member_since
            client_dict["payment_verified"] = cl.payment_verified
            d["client"] = client_dict
        else:
            if client_dict.get("location"):
                client_dict["location"] = format_location(client_dict["location"])
                d["client_location"] = client_dict["location"]
                d["client"] = client_dict

        # E. Client Recent History Contracts
        existing_hist = d.get("client_recent_history") or []
        if soup:
            parsed_hist = parse_client_history(soup)
            if parsed_hist and len(parsed_hist) >= len(existing_hist):
                hist_items = [h.model_dump(mode="json") for h in parsed_hist]
                d["client_recent_history"] = hist_items
                history_fixed_count += 1

        new_jj_str = json.dumps(d, default=str)
        # Store html into DB if DB was empty
        new_raw_html = db_raw if (db_raw and len(db_raw) > 0) else (html_content or "")
        batch_updates.append((new_jj_str, new_raw_html, jid))
        updated_count += 1

        if len(batch_updates) >= 500:
            c.executemany("UPDATE jobs SET job_json = ?, raw_html = ? WHERE job_id = ?", batch_updates)
            conn.commit()
            batch_updates = []
            elapsed = time.time() - start_time
            rate = updated_count / elapsed
            print(f"  Processed {updated_count:,}/{total_jobs:,} jobs ({updated_count/total_jobs*100:.1f}%) | "
                  f"Titles Fixed: {title_fixed_count:,} | Descs: {desc_fixed_count:,} | {rate:.1f} jobs/s", flush=True)

    if batch_updates:
        c.executemany("UPDATE jobs SET job_json = ?, raw_html = ? WHERE job_id = ?", batch_updates)
        conn.commit()

    conn.close()
    print(f"\n[database_14days.db] COMPLETE: {updated_count:,} jobs updated in {time.time()-start_time:.1f}s.")
    print(f"  - Authentic Titles Fixed: {title_fixed_count:,}")
    print(f"  - Full Descriptions Fixed: {desc_fixed_count:,}")
    print(f"  - Client History Contracts Synced: {history_fixed_count:,}")

    # 4. Synchronize database.db
    if DB_MAIN.exists():
        print(f"\nSynchronizing fixes to {DB_MAIN}...", flush=True)
        conn_src = sqlite3.connect(DB_14DAYS, timeout=60)
        c_src = conn_src.cursor()
        conn_dst = sqlite3.connect(DB_MAIN, timeout=60)
        c_dst = conn_dst.cursor()
        c_dst.execute("PRAGMA journal_mode=WAL")

        src_rows = c_src.execute("SELECT job_id, job_json FROM jobs").fetchall()
        conn_src.close()

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
        print(f"[database.db] Synchronized {len(src_rows):,} rows from database_14days.db.", flush=True)

    # 5. Verify Target Job
    print("\n" + "=" * 75)
    print(">>> VERIFYING TARGET JOB ~022089338363935389527 IN DATABASE <<<")
    print("=" * 75)
    conn = sqlite3.connect(DB_14DAYS)
    r = conn.execute("SELECT job_json, length(raw_html) FROM jobs WHERE job_id = ?", ("~022089338363935389527",)).fetchone()
    conn.close()

    if r:
        target_d = json.loads(r[0])
        print("Job ID:       ~022089338363935389527")
        print("Job Title:    ", repr(target_d.get("job_title")))
        print("Job URL:      ", repr(target_d.get("job_url")))
        print("Client Loc:   ", repr(target_d.get("client_location")))
        print("Client Spend: ", repr(target_d.get("client", {}).get("total_spent")))
        print("History Count:", len(target_d.get("client_recent_history", [])))
        for i, h in enumerate(target_d.get("client_recent_history", [])):
            print(f"  [{i+1}] {h.get('job_title')} | {h.get('rating')}★ | {h.get('amount')} | {repr(h.get('feedback', '')[:50])}")


if __name__ == "__main__":
    main()
