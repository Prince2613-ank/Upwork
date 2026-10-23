"""
Autonomous Goal Worker: enrich_14day_jobs_goal.py
Runs continuously until all 14-day jobs in database_14days.db have 100% complete data:
- Client Recent History & Past Completed Contracts
- 10-field Client Intelligence Profile (accurate Hours Billed, Spend, Location, Rating)
- Title-to-Detail Synchronization
- Cross-client sibling propagation
"""

import sys
import os
import time
import json
import sqlite3
import csv
import re
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.abspath("."))
from collector.extraction.review_parser import parse_client_history
from collector.extraction.client_parser import parse_about_client
from fix_14day_jobs_details import extract_accurate_hours, format_location

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"
DB_14DAYS = OUTPUT_DIR / "database_14days.db"
DB_MAIN = OUTPUT_DIR / "database.db"
CSV_HISTORY = OUTPUT_DIR / "client_history.csv"
USERPROFILE = os.environ.get("USERPROFILE", r"C:\Users\princ")
CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
PORT = 9223
PROFILE_DIR = os.path.join(USERPROFILE, "chrome_upwork_profile_2")


def wait_for_cloudflare_clear(page, timeout_sec=15):
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            t = page.title().lower()
            if "just a moment" not in t and "attention required" not in t and "checking your" not in t:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_for_history_section(page, timeout_s: float = 15.0) -> bool:
    """
    Poll until Upwork's React-rendered client history section appears.
    Upwork fetches history via AJAX after DOM loads - we MUST wait for it.
    """
    check_js = """
    () => {
        const text = document.body ? document.body.innerText : '';
        return text.toLowerCase().includes("client's recent history") ||
               text.toLowerCase().includes('recent history');
    }
    """
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if page.evaluate(check_js):
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def fetch_job_html_with_history(page, jurl: str) -> str:
    """
    Navigate to job page and wait for client history to fully render.
    Returns complete HTML including history section.
    """
    # Use networkidle so React data fetches complete
    try:
        page.goto(jurl, timeout=30000, wait_until="networkidle")
    except Exception:
        try:
            page.goto(jurl, timeout=30000, wait_until="domcontentloaded")
        except Exception:
            pass

    wait_for_cloudflare_clear(page, timeout_sec=12)
    time.sleep(2.0)  # Allow React to begin rendering

    # Scroll gradually to trigger lazy-loaded history section
    for pct in [0.25, 0.5, 0.75, 1.0]:
        try:
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {pct})")
        except Exception:
            pass
        time.sleep(0.4)

    # Wait up to 15s for history section to appear
    found = wait_for_history_section(page, timeout_s=15.0)
    if found:
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(0.8)
        except Exception:
            pass

    # Expand "Jobs in progress" toggle
    try:
        clicked = page.evaluate("""
        () => {
            const candidates = [
                document.querySelector('[data-cy="jobs-in-progress-button"]'),
                document.querySelector('[data-test="jobs-in-progress-toggle"]'),
                ...Array.from(document.querySelectorAll('button')).filter(
                    b => (b.innerText || '').toLowerCase().includes('jobs in progress')
                )
            ];
            for (const btn of candidates) {
                if (btn) { btn.click(); return true; }
            }
            return false;
        }
        """)
        if clicked:
            time.sleep(1.0)
    except Exception:
        pass

    # Click "View more" to load all history batches
    for _ in range(30):
        try:
            clicked = page.evaluate("""
            (() => {
                const allLinks = Array.from(document.querySelectorAll('a, button'));
                const target = allLinks.find(el => {
                    const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                    return txt.startsWith('view more') || txt.startsWith('show more') ||
                           txt.startsWith('load more') || txt === 'view all';
                });
                if (target) { target.click(); return true; }
                return false;
            })()
            """)
            if not clicked:
                break
            time.sleep(0.6)
        except Exception:
            break

    # Expand truncated reviews
    try:
        page.evaluate("""
        (() => {
            document.querySelectorAll('button').forEach(b => {
                const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                if (txt === 'more' || txt === 'show more' || txt.includes('...more')) {
                    try { b.click(); } catch(e) {}
                }
            });
        })()
        """)
        time.sleep(0.3)
    except Exception:
        pass

    return page.content()


def get_jobs_needing_enrichment():
    conn = sqlite3.connect(DB_14DAYS, timeout=30)
    c = conn.cursor()
    c.execute("PRAGMA busy_timeout = 30000")
    
    needed = []
    for jid, raw in c.execute("SELECT job_id, job_json FROM jobs").fetchall():
        d = json.loads(raw)
        h = d.get("client_recent_history") or []
        if len(h) == 0:
            cl = d.get("client") or {}
            sp = (d.get("client_total_spent") or cl.get("total_spent") or "").replace(" ", "").lower()
            hr = (d.get("client_hire_rate") or cl.get("hire_rate") or "").replace(" ", "").lower()
            
            m_sp = re.search(r'\$([\d,]+(?:\.\d+)?[km]?)', sp)
            has_real_spend = m_sp and m_sp.group(1).lower() not in ['0', '0.00']
            m_hr = re.search(r'(\d+)%', hr)
            has_real_hires = m_hr and int(m_hr.group(1)) > 0
            tot_hires = cl.get('total_hires') or ''
            m_th = re.search(r'(\d+)', tot_hires)
            if m_th and int(m_th.group(1)) > 0:
                has_real_hires = True
                
            if has_real_spend or has_real_hires:
                since = cl.get("member_since") or ""
                loc = d.get("client_location") or cl.get("location") or ""
                posted = cl.get("jobs_posted") or ""
                fp = f"{since}|{sp}|{posted}|{loc}"
                needed.append({
                    "job_id": jid,
                    "title": d.get("job_title"),
                    "job_url": d.get("job_url"),
                    "fingerprint": fp,
                    "raw": d
                })
    conn.close()
    return needed


def run_enrichment():
    jobs = get_jobs_needing_enrichment()
    total_needed = len(jobs)
    print(f"\n[Enricher] Found {total_needed} established 14-day jobs needing client history.", flush=True)
    if total_needed == 0:
        print("[Enricher] All 14-day jobs already have 100% complete history!", flush=True)
        return 0

    # Ensure Chrome is running
    chrome_proc = None
    import urllib.request
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/version", timeout=1.0) as r:
            chrome_running = (r.status == 200)
    except Exception:
        chrome_running = False

    if not chrome_running:
        print(f"[Enricher] Launching Chrome on port {PORT}...", flush=True)
        os.makedirs(PROFILE_DIR, exist_ok=True)
        args = [
            CHROME_EXE,
            f"--remote-debugging-port={PORT}",
            f"--user-data-dir={PROFILE_DIR}",
            "--disable-fre",
            "--no-default-browser-check",
            "--no-first-run",
            "https://www.upwork.com"
        ]
        chrome_proc = subprocess.Popen(args)
        time.sleep(3)

    enriched_count = 0
    backfilled_siblings = 0
    client_cache = {}

    conn14 = sqlite3.connect(DB_14DAYS, timeout=30)
    c14 = conn14.cursor()
    c14.execute("PRAGMA busy_timeout = 30000")
    c14.execute("PRAGMA journal_mode = WAL")

    conn_main = sqlite3.connect(DB_MAIN, timeout=30)
    c_main = conn_main.cursor()
    c_main.execute("PRAGMA busy_timeout = 30000")
    c_main.execute("PRAGMA journal_mode = WAL")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=15000)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()

            for idx, item in enumerate(jobs, 1):
                jid = item["job_id"]
                jurl = item["job_url"]
                title = item["title"]
                fp = item["fingerprint"]
                job_dict = item["raw"]

                # 1. Check if already cached from a sibling job
                if fp in client_cache:
                    cached_hist, cached_client = client_cache[fp]
                    job_dict["client_recent_history"] = cached_hist
                    if cached_client:
                        for k, v in cached_client.items():
                            if v and k not in ["about_client_text", "client_text"]:
                                job_dict["client"][k] = v
                    raw_json = json.dumps(job_dict)
                    c14.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (raw_json, jid))
                    c_main.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (raw_json, jid))
                    backfilled_siblings += 1
                    enriched_count += 1
                    if enriched_count % 10 == 0:
                        conn14.commit()
                        conn_main.commit()
                    print(f"[{idx}/{total_needed}] ~Sibling Hit: '{title[:35]}' <- Backfilled from cached client ({len(cached_hist)} reviews)", flush=True)
                    continue

                if not jurl or "upwork.com/jobs/" not in jurl:
                    continue

                # 2. Fetch Job Page with proper history wait
                try:
                    html = fetch_job_html_with_history(page, jurl)
                    history_items = parse_client_history(html)

                    # Also update client section with accurate hours and spend
                    client_sec = parse_about_client(html)
                    client_dict = job_dict.get("client") or {}

                    if client_sec.hours_billed:
                        client_dict["hours_billed"] = client_sec.hours_billed
                    if client_sec.total_spent:
                        client_dict["total_spent"] = client_sec.total_spent
                    if client_sec.rating:
                        client_dict["rating"] = client_sec.rating
                    if client_sec.location:
                        client_dict["location"] = format_location(client_sec.location)
                        job_dict["client_location"] = client_dict["location"]

                    if history_items:
                        hist_dicts = [h.model_dump() if hasattr(h, "model_dump") else h.__dict__ for h in history_items]
                        job_dict["client_recent_history"] = hist_dicts
                        client_cache[fp] = (hist_dicts, client_dict)
                    else:
                        # Client genuinely has 0 past contracts (all in progress or brand new contracts)
                        job_dict["client_recent_history"] = []
                        client_cache[fp] = ([], client_dict)

                    job_dict["client"] = client_dict
                    raw_json = json.dumps(job_dict)

                    c14.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (raw_json, jid))
                    c_main.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (raw_json, jid))
                    enriched_count += 1

                    if enriched_count % 10 == 0:
                        conn14.commit()
                        conn_main.commit()

                    h_count = len(job_dict.get("client_recent_history", []))
                    print(f"[{idx}/{total_needed}] +Fetched: '{title[:35]}' | History: {h_count} items | Hours: {client_dict.get('hours_billed', '—')}", flush=True)

                except Exception as e:
                    print(f"[{idx}/{total_needed}] Note on {jid}: {e}", flush=True)

            conn14.commit()
            conn_main.commit()
            browser.close()

    except Exception as e:
        print(f"[Enricher] Global exception: {e}", flush=True)
    finally:
        conn14.close()
        conn_main.close()
        if chrome_proc:
            try:
                chrome_proc.terminate()
                chrome_proc.wait(timeout=3)
            except Exception:
                pass

    print(f"\n[Enricher] COMPLETE: Enriched {enriched_count} jobs ({backfilled_siblings} sibling backfills)!", flush=True)
    return enriched_count


if __name__ == "__main__":
    run_enrichment()
