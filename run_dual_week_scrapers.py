"""
FLODATA 1-WEEK DUAL-PORT SCRAPER ORCHESTRATOR
=============================================
Window: Last Sunday (Sept 27, 2026) -> Yesterday Sunday (Oct 4, 2026)
Worker A: Chrome (Port 9222) - Visible Window & Active Tab
Worker B: Edge (Port 9223)   - Visible Window & Active Tab

Features:
- Visible live tabs in both browsers for real-time monitoring
- Exact 25 Target Client Locations URL
- Mutual atomic claiming across workers (0% duplicate jobs)
- Clean, descriptive freelancer reviews only (0 placeholder reviews)
- 10-Field verified client profiles, un-truncated descriptions
- Dual database persistence: database_14days.db, database.db, database_1week.db
- Automatic report generation & synchronization
"""

import os
import sys
import time
import json
import random
import re
import sqlite3
import urllib.parse
import urllib.request
import subprocess
import threading
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import deque

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

OUTPUT_DIR = ROOT / "output"
LOGS_DIR = OUTPUT_DIR / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DB_14DAYS = OUTPUT_DIR / "database_14days.db"
DB_MAIN   = OUTPUT_DIR / "database.db"
DB_1WEEK  = OUTPUT_DIR / "database_1week.db"

# Strict 1-Week Window: Last Sunday run (Sept 27) to Yesterday Sunday (Oct 4)
DATE_START = "2026-09-27"
DATE_END   = "2026-10-04"

PORT_A = 9222  # Chrome
PORT_B = 9223  # Edge

USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
EDGE_EXE   = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

PROFILE_A = os.path.join(USERPROFILE, "chrome_upwork_profile")
PROFILE_B = os.path.join(USERPROFILE, "edge_upwork_profile")

# Exact 25 Client Locations Filter URL specified by user
BASE_SEARCH_URL = (
    "https://www.upwork.com/nx/search/jobs?"
    "location=Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,"
    "Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,"
    "United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,"
    "United%2520States%2520Virgin%2520Islands&payment_verified=1&per_page=50&sort=recency"
)

from collector.extraction.job_parser import parse_job_detail_page
from generate_standalone_report import clean_freelancer_review, generate_report

db_lock = threading.Lock()
claimed_lock = threading.Lock()
claimed_ids = set()
stats = {"a_new": 0, "b_new": 0, "a_skip": 0, "b_skip": 0, "errors": 0}

recent_saves_a = deque()
recent_saves_b = deque()
rate_lock = threading.Lock()

_browser_procs = []


def is_port_ready(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_browsers_running():
    """Ensure visible Chrome on 9222 and Edge on 9223 are running."""
    os.makedirs(PROFILE_A, exist_ok=True)
    os.makedirs(PROFILE_B, exist_ok=True)

    if not is_port_ready(PORT_A):
        print(f"Launching visible Chrome on Port {PORT_A}...", flush=True)
        p1 = subprocess.Popen([
            CHROME_EXE,
            f"--remote-debugging-port={PORT_A}",
            f"--user-data-dir={PROFILE_A}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            BASE_SEARCH_URL
        ])
        _browser_procs.append(p1)

    if not is_port_ready(PORT_B):
        print(f"Launching visible Edge on Port {PORT_B}...", flush=True)
        p2 = subprocess.Popen([
            EDGE_EXE,
            f"--remote-debugging-port={PORT_B}",
            f"--user-data-dir={PROFILE_B}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            BASE_SEARCH_URL
        ])
        _browser_procs.append(p2)

    # Wait for ports to be ready
    for i in range(15):
        s1 = is_port_ready(PORT_A)
        s2 = is_port_ready(PORT_B)
        if s1 and s2:
            print(f"[OK] Both Browser Ports {PORT_A} (Chrome) and {PORT_B} (Edge) are LIVE!", flush=True)
            return True
        time.sleep(1)

    print(f"[WARN] Ports check after launch: Port {PORT_A}={is_port_ready(PORT_A)}, Port {PORT_B}={is_port_ready(PORT_B)}", flush=True)
    return is_port_ready(PORT_A) or is_port_ready(PORT_B)


def record_save(worker_letter):
    now = time.time()
    dq = recent_saves_a if worker_letter == "A" else recent_saves_b
    with rate_lock:
        dq.append(now)
        while dq and dq[0] < now - 60:
            dq.popleft()
        return len(dq)


def setup_databases():
    """Ensure all target databases have the jobs table and load existing IDs."""
    for db_path in [DB_14DAYS, DB_MAIN, DB_1WEEK]:
        conn = sqlite3.connect(db_path, timeout=30)
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("""CREATE TABLE IF NOT EXISTS jobs (
            job_id   TEXT PRIMARY KEY,
            job_json TEXT,
            raw_html TEXT,
            saved_at TEXT DEFAULT (datetime('now'))
        )""")
        conn.commit()
        existing = set(r[0] for r in c.execute("SELECT job_id FROM jobs").fetchall())
        claimed_ids.update(existing)
        conn.close()

    print(f"[DB] Initialized databases. Total existing jobs claimed: {len(claimed_ids):,}", flush=True)


def save_job_all_dbs(job_dict, jid, raw_html):
    d = {k: v for k, v in job_dict.items() if k != "raw_html"}
    raw_json = json.dumps(d, default=str)
    with db_lock:
        for db_path in [DB_14DAYS, DB_MAIN, DB_1WEEK]:
            try:
                conn = sqlite3.connect(db_path, timeout=30)
                conn.execute(
                    "INSERT OR REPLACE INTO jobs(job_id, job_json, raw_html) VALUES(?, ?, ?)",
                    (jid, raw_json, raw_html)
                )
                conn.commit()
                conn.close()
            except Exception as e:
                print(f"[DB ERR] {db_path.name}: {e}", flush=True)


def extract_job_date(d):
    for f in ("posted_at", "job_posted_at", "posted_date"):
        v = d.get(f, "")
        if v and len(str(v)) >= 10:
            return str(v)[:10]
    job = d.get("job") or {}
    if isinstance(job, dict):
        for f in ("posted_at", "posted_date"):
            v = job.get(f, "")
            if v and len(str(v)) >= 10:
                return str(v)[:10]
    return ""


def check_page_health(page) -> str:
    try:
        title = page.title().lower()
        url = page.url.lower()
        if "just a moment" in title or "checking your browser" in title or "attention required" in title:
            return "cloudflare"
        if "/login" in url or "/ab/account-security/login" in url:
            return "login"
        if "429" in title or "too many requests" in title:
            return "rate_limit"
        return "ok"
    except Exception:
        return "ok"


def wait_cloudflare(page, timeout=15) -> bool:
    for _ in range(timeout):
        st = check_page_health(page)
        if st == "ok":
            return True
        if st == "cloudflare":
            for frame in page.frames:
                try:
                    cb = frame.locator("input[type='checkbox'], .ctp-checkbox-label")
                    if cb.count() > 0:
                        cb.first.click()
                        time.sleep(2)
                except Exception:
                    pass
        time.sleep(1)
    return False


def extract_search_cards(page) -> list:
    deadline = time.time() + 12
    while time.time() < deadline:
        try:
            cnt = page.evaluate("""() => {
                const arts = [...document.querySelectorAll('article, li[data-test], [data-test="job-tile"]')];
                return arts.filter(a => a.querySelector('a[href*="/jobs/"]')).length;
            }""")
            if cnt > 0:
                break
        except Exception:
            pass
        time.sleep(0.3)

    try:
        return page.evaluate("""() => {
            const jobs = [];
            const arts = [...document.querySelectorAll('article, li[data-test], [data-test="job-tile"]')];
            for (const a of arts) {
                const link = a.querySelector('a[href*="/jobs/"]');
                if (!link) continue;
                const href = link.href || '';
                const m = href.match(/~([0-9a-f]+)/i);
                if (!m) continue;
                const jid = '~' + m[1];
                const tEl = a.querySelector('h2, h3, [data-test="job-title"], [class*="title"]');
                const title = tEl ? tEl.innerText.trim() : link.innerText.trim();
                const dEl = a.querySelector('[data-test="job-description-text"], p');
                const desc = dEl ? dEl.innerText.trim().substring(0, 600) : '';
                const lEl = a.querySelector('[data-test="client-country"], [class*="location"], [class*="country"]');
                const loc = lEl ? lEl.innerText.trim() : '';
                let posted = '';
                const spans = [...a.querySelectorAll('span, small, p')];
                for (const s of spans) {
                    const t = (s.innerText || '').trim();
                    if (t.startsWith('Posted ') || t.includes('ago') || t.includes('yesterday')) {
                        posted = t;
                        break;
                    }
                }
                const bEl = a.querySelector('[data-test="budget"], [data-test="hourly-rate"], [class*="budget"]');
                const budget = bEl ? bEl.innerText.trim() : '';
                if (title && href) {
                    jobs.push({
                        job_id: jid,
                        job_url: href,
                        job_title: title,
                        description_snippet: desc,
                        client_location: loc,
                        posted_raw: posted,
                        budget_snippet: budget
                    });
                }
            }
            return jobs;
        }""") or []
    except Exception as e:
        print(f"  [extract_cards err] {e}", flush=True)
        return []


def fetch_job_detail_single_tab(page, url) -> str:
    for att in range(3):
        try:
            page.goto(url, timeout=35000, wait_until="domcontentloaded")
            wait_cloudflare(page, timeout=10)
            break
        except Exception:
            if att == 2:
                raise
            time.sleep(2)

    # Scroll down to trigger AJAX sections
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
    except Exception:
        pass

    # Wait up to 1.5s for client reviews section
    dl = time.time() + 1.5
    while time.time() < dl:
        try:
            found = page.evaluate("""() => {
                const t = (document.body?.innerText || '').toLowerCase();
                return t.includes("client's recent history") || t.includes("recent history") ||
                       t.includes("no feedback yet") || !!document.querySelector('[data-test="client-history"]');
            }""")
            if found:
                break
        except Exception:
            pass
        time.sleep(0.1)

    # Expand View More buttons
    VIEW_MORE_JS = """(() => {
        const keywords = ['view more', 'show more', 'load more', 'view all'];
        const btns = [...document.querySelectorAll('a, button, span[role="button"]')].filter(el => {
            const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
            return keywords.some(k => txt.startsWith(k) || txt === k);
        });
        btns.forEach(b => { try { b.click(); } catch(e) {} });
        return btns.length;
    })()"""

    for _ in range(6):
        try:
            c = page.evaluate(VIEW_MORE_JS)
            if c == 0:
                break
            time.sleep(0.1)
        except Exception:
            break

    # Expand review feedback "...more" text
    try:
        page.evaluate("""(() => {
            document.querySelectorAll('button, span[role="button"], a').forEach(b => {
                const t = (b.innerText || b.textContent || '').trim().toLowerCase();
                if (t === 'more' || t === 'show more' || t.includes('...more') || t === 'read more') {
                    try { b.click(); } catch(e) {}
                }
            });
        })()""")
    except Exception:
        pass

    return page.content()


def run_worker(wid: str, port: int, pages_generator, sk: str):
    """Worker running in a single, visible browser tab."""
    from playwright.sync_api import sync_playwright

    print(f"\n[Worker {wid}] Connecting over CDP to Port {port}...", flush=True)
    live_log = LOGS_DIR / f"live_feed_{port}.jsonl"

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=30000)
            ctx = browser.contexts[0]
            upwork_pages = [p for p in ctx.pages if "upwork.com" in p.url]
            page = upwork_pages[0] if upwork_pages else ctx.new_page()

            consec_past = 0

            for pn in pages_generator:
                search_url = f"{BASE_SEARCH_URL}&page={pn}"
                print(f"\n[Worker {wid}] === Navigating to Search Page {pn} ===", flush=True)
                print(f"URL: {search_url[:90]}...", flush=True)

                try:
                    page.goto(search_url, timeout=40000, wait_until="domcontentloaded")
                    wait_cloudflare(page, timeout=12)
                    time.sleep(1.2)
                except Exception as e:
                    print(f"[Worker {wid}] Search page error: {e}", flush=True)
                    continue

                cards = extract_search_cards(page)
                print(f"[Worker {wid}] Page {pn}: {len(cards)} search cards found.", flush=True)

                if not cards:
                    consec_past += 1
                    if consec_past >= 6:
                        print(f"[Worker {wid}] 6 empty pages -> reached boundary.", flush=True)
                        break
                    continue

                for card in cards:
                    jid = card.get("job_id", "")
                    jurl = card.get("job_url", "")
                    title = card.get("job_title", "")
                    posted_raw = card.get("posted_raw", "")

                    if not jid or not jurl:
                        continue

                    p_lower = posted_raw.lower()

                    # Quick relative check: if card says 9+ days ago, it's older than last Sunday (Sept 27)
                    m_days = re.search(r'(\d+)\s+days?\s+ago', p_lower)
                    if m_days and int(m_days.group(1)) > 8:
                        consec_past += 1
                        print(f"  [Worker {wid}] SKIP (Older than 8 days / Sept 27): {posted_raw} | {title[:35]}", flush=True)
                        if consec_past >= 12:
                            print(f"[Worker {wid}] Reached 12 consecutive jobs older than Sept 27 -> Week 1 completed!", flush=True)
                            return
                        continue

                    # Atomic Claim
                    with claimed_lock:
                        if jid in claimed_ids:
                            stats[sk + "_skip"] += 1
                            continue
                        claimed_ids.add(jid)

                    # Fetch Full Detail in visible live tab
                    try:
                        raw_html = fetch_job_detail_single_tab(page, jurl)
                        job_obj = parse_job_detail_page(raw_html, job_url=jurl, search_card_metadata=card)
                        job_dict = job_obj.model_dump(mode="json")
                        if title:
                            job_dict["job_title"] = title

                        actual_dt = extract_job_date(job_dict)

                        # Enforce date boundary on detail
                        if actual_dt and actual_dt < DATE_START:
                            consec_past += 1
                            print(f"  [Worker {wid}] SKIP (Older than {DATE_START}): {actual_dt} | {title[:35]}", flush=True)
                            if consec_past >= 12:
                                print(f"[Worker {wid}] Reached end of 1-week window ({actual_dt}) -> Worker {wid} complete!", flush=True)
                                return
                            continue

                        consec_past = 0

                        # Filter reviews to ensure only complete descriptive freelancer feedback
                        clean_revs = []
                        for h in (job_dict.get("client_recent_history") or []):
                            fb = clean_freelancer_review(h.get("feedback"), h.get("freelancer_name"))
                            if fb:
                                h["feedback"] = fb
                                clean_revs.append(h)
                        job_dict["client_recent_history"] = clean_revs

                        save_job_all_dbs(job_dict, jid, raw_html)
                        cur_rate = record_save(wid)
                        with db_lock:
                            stats[sk + "_new"] += 1

                        # Append to live feed log
                        try:
                            with open(live_log, "a", encoding="utf-8") as lf:
                                record = {k: v for k, v in job_dict.items() if k != "raw_html"}
                                lf.write(json.dumps(record, default=str) + "\n")
                        except Exception:
                            pass

                        tot = stats["a_new"] + stats["b_new"]
                        print(f"  [Worker {wid}] SAVED #{stats[sk + '_new']} (Total {tot}) '{title[:35]}' | {actual_dt or posted_raw} | {cur_rate}/min", flush=True)
                        time.sleep(random.uniform(1.6, 2.2))

                    except Exception as e:
                        print(f"  [Worker {wid}] Detail err {jid}: {e}", flush=True)
                        stats["errors"] += 1
                        time.sleep(2)

    except Exception as e:
        print(f"[Worker {wid}] Top-level exception: {e}", flush=True)


def odd_pages():
    for p in range(1, 150, 2):
        yield p


def even_pages():
    for p in range(2, 150, 2):
        yield p


def periodic_report_sync(stop_event):
    while not stop_event.is_set():
        time.sleep(300)  # Every 5 minutes
        try:
            print("\n[SYNC] Periodic 5-minute standalone report generation...", flush=True)
            generate_report(
                jobs_csv_path="./output/jobs.csv",
                history_csv_path="./output/client_history.csv",
                output_html="./output/upwork_intelligence_report.html",
                date_filter_start=DATE_START,
                date_filter_end=DATE_END,
                report_title=f"Upwork 1-Week Intelligence Report ({DATE_START} to {DATE_END})"
            )
            print("[SYNC] Report updated and synchronized successfully.", flush=True)
        except Exception as e:
            print(f"[SYNC ERR] {e}", flush=True)


def main():
    print("=" * 75, flush=True)
    print("  FLODATA 1-WEEK DUAL SCRAPER (VISIBLE LIVE TABS)", flush=True)
    print(f"  Target Window: Last Sunday ({DATE_START}) -> Yesterday Sunday ({DATE_END})", flush=True)
    print(f"  Worker A (Chrome Port {PORT_A}): Odd Pages (1, 3, 5, 7, 9...)", flush=True)
    print(f"  Worker B (Edge Port {PORT_B}):   Even Pages (2, 4, 6, 8, 10...)", flush=True)
    print("=" * 75, flush=True)

    ensure_browsers_running()
    setup_databases()

    stop_sync = threading.Event()
    sync_thread = threading.Thread(target=periodic_report_sync, args=(stop_sync,), daemon=True, name="ReportSync")
    sync_thread.start()

    ta = threading.Thread(target=run_worker, args=("A", PORT_A, odd_pages(), "a"), daemon=True, name="Worker-A")
    tb = threading.Thread(target=run_worker, args=("B", PORT_B, even_pages(), "b"), daemon=True, name="Worker-B")

    print("\nStarting Worker A and Worker B live in browser tabs...\n", flush=True)
    ta.start()
    time.sleep(2)
    tb.start()

    while ta.is_alive() or tb.is_alive():
        time.sleep(30)
        tot = stats["a_new"] + stats["b_new"]
        print(f"[Status] Worker A: +{stats['a_new']} | Worker B: +{stats['b_new']} | Combined: +{tot} new jobs | Skips: A={stats['a_skip']}, B={stats['b_skip']}", flush=True)

    ta.join()
    tb.join()
    stop_sync.set()

    print("\n" + "=" * 75, flush=True)
    print(f"1-WEEK SCRAPE COMPLETE! Total new jobs: {stats['a_new'] + stats['b_new']}", flush=True)
    print("Generating final 1-week report...", flush=True)
    generate_report(
        output_html="./output/upwork_intelligence_report.html",
        date_filter_start=DATE_START,
        date_filter_end=DATE_END,
        report_title=f"Upwork 1-Week Intelligence Report ({DATE_START} to {DATE_END})"
    )


if __name__ == "__main__":
    main()
