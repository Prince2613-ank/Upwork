"""
FLODATA 1-WEEK COUNTRY-WISE DUAL SCRAPER & DASHBOARD ORCHESTRATOR
=================================================================
Window: Last Sunday (Sept 27, 2026) -> Yesterday Sunday (Oct 4, 2026)
Filter: 25 Target Filter Countries / Regions (Country-by-Country Split)
Ports:  Worker A on Port 9222 (Chrome)
        Worker B on Port 9223 (Edge / Chrome 2)
Web UI: Localhost Dashboard on http://localhost:8000
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
from queue import Queue, Empty
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
DB_7DAYS  = OUTPUT_DIR / "database_7days.db"

# Dynamic Date Range Filter: Last Sunday (Oct 4) to Yesterday Sunday (Oct 11)
import argparse
_parser = argparse.ArgumentParser(description="Flodata Upwork Intelligence Dual Scraper")
_parser.add_argument("--start", default="2026-10-04", help="Start Date YYYY-MM-DD")
_parser.add_argument("--end", default="2026-10-11", help="End Date YYYY-MM-DD")
_args, _ = _parser.parse_known_args()

DATE_START = _args.start
DATE_END   = _args.end

PORT_A = 9222  # Chrome
PORT_B = 9223  # Edge / Chrome 2

# 25 Target Filter Locations from User's exact URL
# 25 Target Filter Locations - prioritize 17 unharvested countries first
TARGET_COUNTRIES = [
    "Singapore",
    "Japan",
    "South Korea",
    "Hong Kong",
    "Israel",
    "Qatar",
    "Kuwait",
    "Bahrain",
    "Malaysia",
    "Morocco",
    "New Zealand",
    "Belgium",
    "Bahamas",
    "Cayman Islands",
    "American Samoa",
    "United States Minor Outlying Islands",
    "United States Virgin Islands",
    "Canada",
    "United States",
    "United Kingdom",
    "Australia and New Zealand",
    "Europe",
    "India",
    "United Arab Emirates",
    "Saudi Arabia",
]

from collector.extraction.job_parser import parse_job_detail_page
from collector.scraper_manager import scraper_manager
from generate_standalone_report import clean_freelancer_review, generate_report

db_lock = threading.Lock()
claimed_lock = threading.Lock()
claimed_ids = set()
stats = {"a_new": 0, "b_new": 0, "a_skip": 0, "b_skip": 0, "errors": 0}

recent_saves_a = deque()
recent_saves_b = deque()
rate_lock = threading.Lock()

country_queue = Queue()
for c in TARGET_COUNTRIES:
    country_queue.put(c)

queue_lock = threading.Lock()
sweep_counter = {"count": 1}

def is_endpoint_ready(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(f"{endpoint}/json/version", timeout=1.5) as r:
            return r.status == 200
    except Exception:
        return False

def is_port_ready(port: int) -> bool:
    for host in ["localhost", "127.0.0.1", "[::1]"]:
        if is_endpoint_ready(f"http://{host}:{port}"):
            return True
    return False

def get_endpoint_a():
    """Worker A (Chrome): checks 127.0.0.1:9222 first, then [::1]:9223 (Chrome IPv6)."""
    if is_endpoint_ready("http://127.0.0.1:9222"):
        return "http://127.0.0.1:9222", "Chrome (Port 9222)"
    if is_endpoint_ready("http://[::1]:9223"):
        return "http://[::1]:9223", "Chrome (Port 9223 IPv6)"
    return None, None

def get_endpoint_b():
    """Worker B (Edge): checks 127.0.0.1:9223 (Edge IPv4)."""
    if is_endpoint_ready("http://127.0.0.1:9223"):
        return "http://127.0.0.1:9223", "Edge (Port 9223 IPv4)"
    return None, None


def record_save(worker_letter):
    now = time.time()
    dq = recent_saves_a if worker_letter == "A" else recent_saves_b
    with rate_lock:
        dq.append(now)
        while dq and dq[0] < now - 60:
            dq.popleft()
        return len(dq)

def get_target_delay(worker_letter):
    """
    Dynamically regulate pacing to target jobs/min combined.
    Dynamically reads target from pacing.json on every save.
    """
    target_combined = 28.0
    delay_override = None
    try:
        pacing_file = ROOT / "pacing.json"
        if pacing_file.exists():
            with open(pacing_file, "r") as f:
                cfg = json.load(f)
                target_combined = float(cfg.get("target_jobs_per_minute", 28.0))
                if "delay_between_jobs" in cfg:
                    delay_override = float(cfg["delay_between_jobs"])
    except Exception:
        pass

    now = time.time()
    with rate_lock:
        rate_a = sum(1 for t in recent_saves_a if t > now - 60)
        rate_b = sum(1 for t in recent_saves_b if t > now - 60)
        current_combined = rate_a + rate_b

    if delay_override is not None:
        jitter = random.uniform(-0.2, 0.2)
        return max(1.0, delay_override + jitter), current_combined

    # Optimal base sleep: target per worker = target / 2. Overhead is ~2.4s.
    target_per_worker = max(1.0, target_combined / 2.0)
    cycle_time = 60.0 / target_per_worker
    base_sleep = max(1.2, cycle_time - 2.4)

    if current_combined >= target_combined:
        excess = current_combined - target_combined
        sleep_sec = base_sleep + min(4.0, (excess + 1) * 0.5)
    elif current_combined <= target_combined - 3:
        sleep_sec = max(1.2, base_sleep - 0.4)
    else:
        sleep_sec = base_sleep

    jitter = random.uniform(-0.25, 0.25)
    delay = max(1.0, sleep_sec + jitter)
    return delay, current_combined

def setup_databases():
    """Ensure all target databases have the jobs table and load existing IDs strictly from 1-week DB."""
    for db_path in [DB_14DAYS, DB_MAIN]:
        try:
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
            conn.close()
        except Exception:
            pass

    # DB_1WEEK: Claim ONLY what is already in database_1week.db
    conn = sqlite3.connect(DB_1WEEK, timeout=30)
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

    print(f"[DB] Initialized databases. Total existing jobs claimed from 1-week DB: {len(claimed_ids):,}", flush=True)

def save_job_all_dbs(job_dict, jid, raw_html, actual_dt=""):
    d = {k: v for k, v in job_dict.items() if k != "raw_html"}
    loc = str(d.get("client_location") or "")
    desc = (d.get("job") or {}).get("description") or d.get("description_snippet") or d.get("description") or ""
    # Reject Cloudflare challenge pages or blank job descriptions
    if "Enable JavaScript" in loc or "Just a moment" in loc or not desc.strip():
        return

    raw_json = json.dumps(d, default=str)
    with db_lock:
        # DB_14DAYS has raw_html
        try:
            conn = sqlite3.connect(DB_14DAYS, timeout=30)
            conn.execute(
                "INSERT OR REPLACE INTO jobs(job_id, job_json, raw_html) VALUES(?, ?, ?)",
                (jid, raw_json, raw_html)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            print(f"[DB ERR] {DB_14DAYS.name}: {e}", flush=True)

        # DB_1WEEK & DB_7DAYS: STRICTLY Last Sunday to Yesterday Sunday (2026-10-04 to 2026-10-11)
        if not actual_dt or (DATE_START <= actual_dt <= DATE_END):
            for db_target in [DB_1WEEK, DB_7DAYS]:
                try:
                    conn = sqlite3.connect(db_target, timeout=30)
                    conn.execute(
                        "INSERT OR REPLACE INTO jobs(job_id, job_json, raw_html) VALUES(?, ?, ?)",
                        (jid, raw_json, raw_html)
                    )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    print(f"[DB ERR] {db_target.name}: {e}", flush=True)

        # DB_MAIN has job_id, job_json
        try:
            conn = sqlite3.connect(DB_MAIN, timeout=30)
            conn.execute(
                "INSERT OR REPLACE INTO jobs(job_id, job_json) VALUES(?, ?)",
                (jid, raw_json)
            )
            conn.commit()
            conn.close()
        except Exception:
            pass

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
    deadline = time.time() + 10
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
        return []

def fetch_job_detail_single_tab(page, url) -> str:
    for att in range(2):
        try:
            page.goto(url, timeout=15000, wait_until="domcontentloaded")
            wait_cloudflare(page, timeout=8)
            break
        except Exception:
            if att == 1:
                raise
            time.sleep(1)

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

    for _ in range(5):
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

def run_worker_country_stream(wid: str, endpoint: str, sk: str, desc: str = ""):
    """Worker running country-by-country on a live browser tab."""
    from playwright.sync_api import sync_playwright

    print(f"\n[Worker {wid}] Connecting over CDP to {endpoint} ({desc})...", flush=True)
    live_log = LOGS_DIR / f"live_feed_{wid.lower()}.jsonl"

    def get_working_page(ctx):
        for p in ctx.pages:
            try:
                if not p.is_closed():
                    return p
            except Exception:
                pass
        return ctx.new_page()

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(endpoint, timeout=30000)
            ctx = browser.contexts[0]
            upwork_pages = [p for p in ctx.pages if not p.is_closed() and "upwork.com" in p.url]
            page = upwork_pages[0] if upwork_pages else get_working_page(ctx)

            while True:
                with queue_lock:
                    if country_queue.empty():
                        sweep_counter["count"] += 1
                        print("\n" + "=" * 75, flush=True)
                        print(f"  [SWEEPER] All 25 countries completed! Starting Sweep #{sweep_counter['count']}", flush=True)
                        print(f"  Re-scanning all 25 countries from Page 1 to ensure ZERO jobs are left behind...", flush=True)
                        print("=" * 75 + "\n", flush=True)
                        for c in TARGET_COUNTRIES:
                            country_queue.put(c)
                        time.sleep(3)

                try:
                    country = country_queue.get(timeout=5)
                except Empty:
                    time.sleep(2)
                    continue

                encoded_country = urllib.parse.quote(country)
                base_country_url = f"https://www.upwork.com/nx/search/jobs?location={encoded_country}&payment_verified=1&per_page=50&sort=recency"

                print(f"\n===========================================================", flush=True)
                print(f"[Worker {wid}] TARGET COUNTRY: {country.upper()}", flush=True)
                print(f"===========================================================", flush=True)

                consec_past = 0
                consec_timeouts = 0

                for pn in range(1, 51):
                    search_url = f"{base_country_url}&page={pn}"
                    print(f"\n[Worker {wid}] [{country}] === Search Page {pn} ===", flush=True)

                    st = scraper_manager.worker_a_status if wid == "A" else scraper_manager.worker_b_status
                    st["online"] = True
                    st["country"] = country
                    st["page"] = pn
                    st["action"] = f"Searching {country} (Page {pn})"
                    st["saved"] = stats[sk + "_new"]
                    st["skips"] = stats[sk + "_skip"]
                    scraper_manager.stats[sk + "_new"] = stats[sk + "_new"]
                    scraper_manager.stats[sk + "_skip"] = stats[sk + "_skip"]
                    scraper_manager.log(f"[Worker {wid}] [{country}] === Search Page {pn} ===")

                    try:
                        if page.is_closed():
                            page = get_working_page(ctx)
                        page.goto(search_url, timeout=25000, wait_until="domcontentloaded")
                        wait_cloudflare(page, timeout=10)
                        time.sleep(1.0)
                    except Exception as e:
                        consec_timeouts += 1
                        err_msg = f"[Worker {wid}] Search page error: {e}. Recovering page ({consec_timeouts}/3)..."
                        print(err_msg, flush=True)
                        scraper_manager.log(err_msg)
                        st["action"] = "Recovering page..."
                        try:
                            if not page.is_closed():
                                page.goto("about:blank", timeout=5000)
                        except Exception:
                            pass
                        time.sleep(1.5)
                        if consec_timeouts >= 3:
                            print(f"[Worker {wid}] [{country}] 3 consecutive timeouts/errors on search pages -> Moving to next country!", flush=True)
                            scraper_manager.log(f"[Worker {wid}] [{country}] 3 consecutive timeouts -> Next country!")
                            break
                        continue

                    # Handle Login Screen Gracefully (do NOT crash or exit)
                    if "/login" in page.url.lower() or "login" in page.title().lower():
                        print(f"[Worker {wid}] Login prompt detected on {country} Page {pn}. Waiting for user login...", flush=True)
                        scraper_manager.log(f"⚠️ [Worker {wid}] Login prompt detected on {country} Page {pn}. Waiting for user login...")
                        st["action"] = "Waiting for login..."
                        for _ in range(60):
                            time.sleep(2)
                            if "/login" not in page.url.lower():
                                break
                        continue

                    cards = extract_search_cards(page)
                    print(f"[Worker {wid}] [{country}] Page {pn}: {len(cards)} search cards found.", flush=True)

                    if not cards:
                        consec_past += 1
                        if consec_past >= 3:
                            print(f"[Worker {wid}] [{country}] End of search results reached -> Moving to next country!", flush=True)
                            break
                        continue

                    consec_timeouts = 0
                    country_cutoff = False

                    for card in cards:
                        jid = card.get("job_id", "")
                        jurl = card.get("job_url", "")
                        title = card.get("job_title", "")
                        posted_raw = card.get("posted_raw", "")

                        if not jid or not jurl:
                            continue

                        p_lower = posted_raw.lower()

                        # Fast Check: If posted minutes or <= 16 hours ago, it's today (Monday Oct 12) -> Skip instantly in 0ms!
                        m_hours = re.search(r'(\d+)\s+hours?\s+ago', p_lower)
                        if ("minute" in p_lower or "second" in p_lower or "just now" in p_lower or (m_hours and int(m_hours.group(1)) <= 16)):
                            stats[sk + "_skip"] += 1
                            st["skips"] = stats[sk + "_skip"]
                            continue

                        # If relative date is 9+ days ago (Saturday Oct 3 or older), it is older than Sunday Oct 4
                        m_days = re.search(r'(\d+)\s+days?\s+ago', p_lower)
                        if m_days and int(m_days.group(1)) >= 9:
                            consec_past += 1
                            stats[sk + "_skip"] += 1
                            st["skips"] = stats[sk + "_skip"]
                            if consec_past >= 6:
                                print(f"[Worker {wid}] [{country}] 6 consecutive jobs older than {DATE_START} ({posted_raw}) -> Country {country} 7-day complete!", flush=True)
                                scraper_manager.log(f"🏁 [Worker {wid}] [{country}] 6 consecutive jobs older than {DATE_START} -> Country complete!")
                                country_cutoff = True
                                break
                            continue

                        # Atomic Claim
                        with claimed_lock:
                            if jid in claimed_ids:
                                stats[sk + "_skip"] += 1
                                st["skips"] = stats[sk + "_skip"]
                                continue
                            claimed_ids.add(jid)

                        # Fetch Full Detail in visible live tab
                        try:
                            st["action"] = f"Extracting: {title[:28]}"
                            raw_html = fetch_job_detail_single_tab(page, jurl)
                            job_obj = parse_job_detail_page(raw_html, job_url=jurl, search_card_metadata=card)
                            job_dict = job_obj.model_dump(mode="json")
                            if title:
                                job_dict["job_title"] = title

                            actual_dt = extract_job_date(job_dict)

                            # Enforce UPPER BOUND (Strict Sunday Oct 11 cutoff - skip today's jobs)
                            if actual_dt and actual_dt > DATE_END:
                                print(f"  [Worker {wid}] [{country}] SKIP (Today's Job - Newer than Sunday {DATE_END}): {actual_dt} | {title[:32]}", flush=True)
                                stats[sk + "_skip"] += 1
                                st["skips"] = stats[sk + "_skip"]
                                continue

                            # Enforce LOWER BOUND (Strict Sunday Oct 04 cutoff)
                            if actual_dt and actual_dt < DATE_START:
                                consec_past += 1
                                stats[sk + "_skip"] += 1
                                st["skips"] = stats[sk + "_skip"]
                                print(f"  [Worker {wid}] [{country}] SKIP (Older than {DATE_START}): {actual_dt} | {title[:32]}", flush=True)
                                if consec_past >= 6:
                                    print(f"[Worker {wid}] [{country}] Reached end of 7-day window ({actual_dt}) -> Country {country} complete!", flush=True)
                                    scraper_manager.log(f"🏁 [Worker {wid}] [{country}] Reached end of 7-day window ({actual_dt}) -> Country complete!")
                                    country_cutoff = True
                                    break
                                continue

                            consec_past = 0

                            # Strict review constraint: only complete descriptive freelancer feedback
                            clean_revs = []
                            for h in (job_dict.get("client_recent_history") or []):
                                fb = clean_freelancer_review(h.get("feedback"), h.get("freelancer_name"))
                                if fb:
                                    h["feedback"] = fb
                                    clean_revs.append(h)
                            job_dict["client_recent_history"] = clean_revs

                            save_job_all_dbs(job_dict, jid, raw_html, actual_dt)
                            cur_rate = record_save(wid)
                            with db_lock:
                                stats[sk + "_new"] += 1

                            st["saved"] = stats[sk + "_new"]
                            st["action"] = f"Saved: {title[:28]}"
                            scraper_manager.stats[sk + "_new"] = stats[sk + "_new"]

                            # Append to live feed log
                            try:
                                with open(live_log, "a", encoding="utf-8") as lf:
                                    record = {k: v for k, v in job_dict.items() if k != "raw_html"}
                                    lf.write(json.dumps(record, default=str) + "\n")
                            except Exception:
                                pass

                            tot = stats["a_new"] + stats["b_new"]
                            delay_sec, comb_rate = get_target_delay(wid)
                            save_line = f"  [Worker {wid}] [{country}] SAVED #{stats[sk + '_new']} (Total {tot}) '{title[:30]}' | {actual_dt or posted_raw} | Rate: {comb_rate}/min | Pacing: {delay_sec:.1f}s"
                            print(save_line, flush=True)
                            scraper_manager.log(f"💾 [Worker {wid}] [{country}] Saved #{stats[sk + '_new']} (Total {tot}) '{title[:28]}' | {actual_dt or posted_raw}")

                            try:
                                scraper_manager._update_tab_hud(page, wid, country, pn, f"Saved: {title[:28]}", st["saved"])
                            except Exception:
                                pass

                            time.sleep(delay_sec)

                        except Exception as e:
                            print(f"  [Worker {wid}] Detail err {jid}: {e}", flush=True)
                            stats["errors"] += 1
                            st["action"] = f"Error: {str(e)[:24]}"
                            time.sleep(1.5)

                    if country_cutoff:
                        break

    except Exception as e:
        print(f"[Worker {wid}] Exception: {e}", flush=True)

def run_dashboard_server():
    """Run Section 17 interactive local web dashboard."""
    try:
        import uvicorn
        print("\n[DASHBOARD] Starting Local Web Dashboard on http://127.0.0.1:8000...", flush=True)
        uvicorn.run("collector.dashboard.app:app", host="0.0.0.0", port=8000, log_level="warning")
    except Exception as e:
        print(f"[DASHBOARD] Notice: {e}", flush=True)

def supervisor_a_launcher():
    """Supervises Worker A and starts it as soon as Chrome CDP endpoint is ready."""
    started = False
    while not started:
        ep, desc = get_endpoint_a()
        if ep:
            print(f"\n[OK] {desc} detected online! Starting Worker A...", flush=True)
            t = threading.Thread(target=run_worker_country_stream, args=("A", ep, "a", desc), daemon=True)
            t.start()
            started = True
            break
        time.sleep(3)

def supervisor_b_launcher():
    """Supervises Worker B and starts it as soon as Edge CDP endpoint is ready."""
    started = False
    while not started and not country_queue.empty():
        ep, desc = get_endpoint_b()
        if ep:
            print(f"\n[OK] {desc} detected online! Starting Worker B...", flush=True)
            t = threading.Thread(target=run_worker_country_stream, args=("B", ep, "b", desc), daemon=True)
            t.start()
            started = True
            break
        time.sleep(3)

def periodic_reporter():
    """Auto-generates reports every 5 minutes."""
    while True:
        time.sleep(300)
        tot = stats["a_new"] + stats["b_new"]
        if tot > 0:
            try:
                print("\n[REPORT] Generating updated 7-day report from database_1week.db...", flush=True)
                generate_report(
                    output_html=str(OUTPUT_DIR / "upwork_1week_report.html"),
                    db_path=str(DB_1WEEK),
                    report_title="Upwork 7-Day Market Intelligence Report (Oct 04 - Oct 11, 2026)"
                )
                from collector.dashboard.app import _export_1week_csv
                _export_1week_csv(OUTPUT_DIR / "jobs_1week.csv")
                print("[REPORT] Updated 7-day HTML reports & jobs_1week.csv", flush=True)
            except Exception as e:
                print(f"[REPORT ERR] {e}", flush=True)

def main():
    print("=" * 75)
    print("  FLODATA 7-DAY COUNTRY-WISE DUAL SCRAPER & LOCALHOST DASHBOARD")
    print(f"  Target Window: Last Sunday ({DATE_START}) -> Yesterday Sunday ({DATE_END})")
    print(f"  Queue: {len(TARGET_COUNTRIES)} Country/Region Filters")
    print(f"  Worker A (Chrome): Auto-detected (Port 9222 / IPv6 9223)")
    print(f"  Worker B (Edge):   Auto-detected (Port 9223 IPv4)")
    print(f"  Dashboard:         http://localhost:8000")
    print("=" * 75)

    setup_databases()

    # 1. Initialize Scraper Manager State for Web Dashboard
    scraper_manager.is_running = True
    scraper_manager.date_start = DATE_START
    scraper_manager.date_end = DATE_END
    scraper_manager.start_time = time.time()
    scraper_manager.countries = list(TARGET_COUNTRIES)
    scraper_manager.stats["sweep"] = sweep_counter["count"]

    # 2. Start Dashboard Server in background thread
    t_dash = threading.Thread(target=run_dashboard_server, daemon=True)
    t_dash.start()
    time.sleep(1.5)

    # 2. Start Periodic Reporter thread
    t_rep = threading.Thread(target=periodic_reporter, daemon=True)
    t_rep.start()

    # 3. Check / Start Worker A (Chrome)
    ep_a, desc_a = get_endpoint_a()
    if ep_a:
        print(f"[OK] {desc_a} is ready. Starting Worker A...", flush=True)
        t_a = threading.Thread(target=run_worker_country_stream, args=("A", ep_a, "a", desc_a), daemon=True)
        t_a.start()
    else:
        print(f"[INFO] Chrome CDP not yet online. Background supervisor will auto-attach Worker A when ready.", flush=True)
        t_sup_a = threading.Thread(target=supervisor_a_launcher, daemon=True)
        t_sup_a.start()

    # 4. Check / Start Worker B (Edge)
    ep_b, desc_b = get_endpoint_b()
    if ep_b:
        print(f"[OK] {desc_b} is ready. Starting Worker B...", flush=True)
        t_b = threading.Thread(target=run_worker_country_stream, args=("B", ep_b, "b", desc_b), daemon=True)
        t_b.start()
    else:
        print(f"[INFO] Edge CDP not yet online. Background supervisor will auto-attach Worker B when ready.", flush=True)
        t_sup = threading.Thread(target=supervisor_b_launcher, daemon=True)
        t_sup.start()


    # Keep Main Process Alive indefinitely
    start_time = time.time()
    while True:
        time.sleep(15)
        tot = stats["a_new"] + stats["b_new"]
        elapsed = int(time.time() - start_time)
        rem_countries = country_queue.qsize()
        print(
            f"[STATUS {elapsed}s] New Jobs: Total={tot} (A={stats['a_new']}, B={stats['b_new']}) | "
            f"Skips: (A={stats['a_skip']}, B={stats['b_skip']}) | Remaining Countries: {rem_countries}/25 | Sweep: #{sweep_counter['count']}",
            flush=True
        )

if __name__ == "__main__":
    main()
