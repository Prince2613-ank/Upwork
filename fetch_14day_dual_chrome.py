"""
FLODATA 14-DAY DUAL-PORT COUNTRY-BY-COUNTRY SCRAPER (v6)
========================================================
- Country-by-country crawling: Worker A and Worker B each take 1 country at a time
- When all 14-day jobs (Sept 13 -> Sept 27) are fetched from Country 1, moves to Country 2
- Strictly SINGLE TAB in Chrome (Port 9222) and SINGLE TAB in Chrome (Port 9224)
- Never opens multiple tabs
- Strict filters: payment_verified=1, sort=recency
- Speed: strictly 6-7 jobs/min per port (Combined: 12-14 jobs/min)
- Full capture: 150+ contract history items, reviews un-truncated, raw HTML preserved
"""

import os, sys, time, json, random, re, threading, sqlite3, urllib.parse, urllib.request, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import deque

CHROME_EXE = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
CHROME_B_PROFILE = r"C:\chrome_b_9224_scraper"
_chrome_b_proc = None  # global handle to keep Chrome B alive

def launch_chrome_b():
    """Launch a fresh Chrome instance on port 9224 with isolated profile."""
    global _chrome_b_proc
    # Kill any previous instance
    if _chrome_b_proc and _chrome_b_proc.poll() is None:
        try: _chrome_b_proc.terminate()
        except Exception: pass
    # Wipe profile to prevent lock conflicts
    import shutil
    if os.path.exists(CHROME_B_PROFILE):
        try: shutil.rmtree(CHROME_B_PROFILE, ignore_errors=True)
        except Exception: pass
    args = [
        CHROME_EXE,
        f"--remote-debugging-port={PORT_B}",
        f"--user-data-dir={CHROME_B_PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-component-update",
        "--disable-background-mode",
        "--window-size=1280,800",
        "about:blank"
    ]
    _chrome_b_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"  [Chrome-B] Launched PID={_chrome_b_proc.pid} on port {PORT_B}", flush=True)
    # Wait for CDP to be ready
    for _ in range(20):
        time.sleep(1)
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{PORT_B}/json/version", timeout=2).read()
            print(f"  [Chrome-B] CDP ready on port {PORT_B}", flush=True)
            return True
        except Exception:
            pass
    print(f"  [!!] Chrome-B failed to bind port {PORT_B}", flush=True)
    return False

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

DB_MAIN   = ROOT / "output" / "database.db"
DB_14DAYS = ROOT / "output" / "database_14days.db"

# Fixed 14-day window: Sept 13 -> Sept 27 (excluding Sept 28+)
DATE_END   = "2026-09-27"
DATE_START = "2026-09-13"

PORT_A = 9222  # Chrome
PORT_B = 9223  # Edge (working again)

MAX_PAGES = 150

# ── Non-Overlapping Country Lists (Country-by-Country) ──────────────────────
COUNTRIES_A = [
    "Portugal",
    "Greece",
    "Czech Republic",
    "Romania",
    "Hungary",
    "Turkey",
    "Croatia",
    "Estonia",
    "Latvia",
    "Lithuania",
    "Slovakia",
    "Slovenia",
    "Bulgaria",
    "Iceland"
]

COUNTRIES_B = [
    "Brazil",
    "Mexico",
    "Argentina",
    "Chile",
    "Colombia",
    "Costa Rica",
    "Panama",
    "Uruguay",
    "Peru",
    "Philippines",
    "Pakistan",
    "Thailand",
    "Indonesia",
    "Vietnam",
    "Egypt",
    "Nigeria",
    "Kenya",
    "Bahrain",
    "Oman"
]

# Starting page map: skip already-scraped pages where applicable
START_PAGES = {}

from collector.extraction.job_parser import parse_job_detail_page

db_lock      = threading.Lock()
claimed_lock = threading.Lock()
claimed_ids  = set()
stats        = {"a_new":0, "b_new":0, "a_skip":0, "b_skip":0, "errors":0}

# ─── Speed Monitoring (Rolling 60-Second Window) ─────────────────────────────
recent_saves_a = deque()
recent_saves_b = deque()
rate_lock = threading.Lock()

def record_save(worker_letter):
    now = time.time()
    dq = recent_saves_a if worker_letter == "A" else recent_saves_b
    with rate_lock:
        dq.append(now)
        while dq and dq[0] < now - 60:
            dq.popleft()
        return len(dq)

# Pacing tuned for ~15 jobs/min combined (~7.5 jobs/min per port)
def jitter_search(): time.sleep(random.uniform(0.8, 1.4))
def jitter_detail(): time.sleep(random.uniform(1.8, 2.3))

def backoff(att):
    w = [30, 60, 120][min(att, 2)]
    print(f"  [backoff] {w}s...", flush=True)
    time.sleep(w)


# ─── DB Setup & Seeding ───────────────────────────────────────────────────────

def setup_db():
    print("="*70, flush=True)
    print(f"[DB] Setting up | Window: {DATE_START} -> {DATE_END}", flush=True)
    conn = sqlite3.connect(DB_14DAYS, timeout=30)
    c    = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("""CREATE TABLE IF NOT EXISTS jobs (
        job_id   TEXT PRIMARY KEY,
        job_json TEXT,
        raw_html TEXT,
        saved_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.commit()

    seeded = 0
    if DB_MAIN.exists():
        for jid, raw in sqlite3.connect(DB_MAIN, timeout=30).execute(
                "SELECT job_id, job_json FROM jobs").fetchall():
            try:
                d  = json.loads(raw)
                dt = _date(d)
                if dt and DATE_START <= dt <= DATE_END:
                    rh = d.pop("raw_html", "") or ""
                    c.execute("INSERT OR IGNORE INTO jobs(job_id,job_json,raw_html) VALUES(?,?,?)",
                              (jid, json.dumps(d, default=str), rh))
                    seeded += 1
            except Exception: pass
        conn.commit()

    total = c.execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    existing = set(r[0] for r in c.execute("SELECT job_id FROM jobs").fetchall())
    conn.close()
    print(f"[DB] DB Total: {total:,} (seeded from 1mo: {seeded:,})", flush=True)
    claimed_ids.update(existing)
    return existing


def save_job(job_dict, jid, raw_html):
    d = {k:v for k,v in job_dict.items() if k != "raw_html"}
    conn = sqlite3.connect(DB_14DAYS, timeout=30)
    conn.execute("INSERT OR REPLACE INTO jobs(job_id,job_json,raw_html) VALUES(?,?,?)",
                 (jid, json.dumps(d, default=str), raw_html))
    conn.commit()
    conn.close()


def _date(d):
    for f in ("posted_at","job_posted_at","posted_date"):
        v = d.get(f,"")
        if v and len(str(v))>=10: return str(v)[:10]
    job = d.get("job") or {}
    if isinstance(job, dict):
        for f in ("posted_at","posted_date"):
            v = job.get(f,"")
            if v and len(str(v))>=10: return str(v)[:10]
    return ""


# ── Suspension / Rate-Limit Monitor ──────────────────────────────────────────
SUSPEND_SIGNALS = [
    "account suspended", "account has been suspended",
    "account flagged", "account blocked", "violat",
    "terms of service", "your account has been"
]

def check_page_health(page) -> str:
    try:
        title = page.title().lower()
        url   = page.url.lower()

        if "just a moment" in title or "checking your browser" in title:
            return "cloudflare"
        if "attention required" in title:
            return "cloudflare"
        if "/ab/account-security/login" in url or ("/login" in url and "upwork.com" in url):
            return "login"
        if "429 too many" in title or "too many requests" in title:
            return "rate_limit"

        try:
            is_logged_out = page.evaluate("""() => {
                const nav = document.querySelector('nav, header');
                if (nav) {
                    const txt = (nav.innerText || '').toLowerCase();
                    if (txt.includes('log in') && txt.includes('sign up')) return true;
                }
                return false;
            }""")
            if is_logged_out:
                return "login"
        except Exception: pass

        if any(w in title for w in ("error", "denied", "blocked", "suspended", "security")):
            body = page.evaluate("()=>(document.body?.innerText||'').toLowerCase()") or ""
            if any(s in body for s in SUSPEND_SIGNALS):
                return "suspended"
            if "too many requests" in body:
                return "rate_limit"

        return "ok"
    except Exception:
        return "ok"


def wait_cf(page, timeout=20) -> bool:
    for _ in range(timeout):
        status = check_page_health(page)
        if status == "ok":
            return True
        if status == "suspended":
            print("  [!!] ACCOUNT SUSPENDED DETECTED — stopping!", flush=True)
            return False
        if status == "login":
            print("  [!] Session expired — redirected to login!", flush=True)
            return False
        if status == "rate_limit":
            print("  [!] Real 429 rate limit — waiting 60s...", flush=True)
            time.sleep(60)
            continue
        if status == "cloudflare":
            for frame in page.frames:
                try:
                    cb = frame.locator("input[type='checkbox'],.ctp-checkbox-label")
                    if cb.count() > 0: cb.first.click(); time.sleep(2)
                except Exception: pass
            time.sleep(1)
            continue
        time.sleep(1)
    return False


# ─── Card Extraction (Accurate Relative Time) ────────────────────────────────

def extract_cards(page) -> list:
    """Wait for React job cards, extract metadata and posted relative time via JS."""
    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            n = page.evaluate("""() => {
                const arts=[...document.querySelectorAll('article,li[data-test],[data-test="job-tile"]')];
                return arts.filter(a=>a.querySelector('a[href*="/jobs/"]')).length;
            }""")
            if n > 0: break
        except Exception: pass
        time.sleep(0.3)
    try:
        return page.evaluate("""() => {
            const jobs=[];
            const arts=[...document.querySelectorAll('article,li[data-test],[data-test="job-tile"]')];
            for(const a of arts){
                const link=a.querySelector('a[href*="/jobs/"]'); if(!link) continue;
                const href=link.href||'';
                const m=href.match(/~([0-9a-f]+)/i); if(!m) continue;
                const jid='~'+m[1];
                const tEl=a.querySelector('h2,h3,[data-test="job-title"],[class*="title"]');
                const title=tEl?tEl.innerText.trim():link.innerText.trim();
                const dEl=a.querySelector('[data-test="job-description-text"],p');
                const desc=dEl?dEl.innerText.trim().substring(0,500):'';
                const lEl=a.querySelector('[data-test="client-country"],[class*="location"],[class*="country"]');
                const loc=lEl?lEl.innerText.trim():'';
                let posted='';
                const spans=[...a.querySelectorAll('span, small, p')];
                for(const s of spans){
                    const t=(s.innerText||'').trim();
                    if(t.startsWith('Posted ') || t.includes('ago') || t.includes('yesterday')){
                        posted=t; break;
                    }
                }
                const bEl=a.querySelector('[data-test="budget"],[data-test="hourly-rate"],[class*="budget"]');
                const budget=bEl?bEl.innerText.trim():'';
                if(title&&href) jobs.push({job_id:jid,job_url:href,job_title:title,
                    description_snippet:desc,client_location:loc,posted_raw:posted,budget_snippet:budget});
            }
            return jobs;
        }""") or []
    except Exception as e:
        print(f"  [extract_cards] {e}", flush=True); return []


# ─── Full Detail Fetch (Single Tab Navigation) ──────────────────────────────

def fetch_full_detail(page, url) -> str:
    """
    Full capture in the SAME tab:
    - Fast domcontentloaded navigation
    - Quick health check
    - Scrolls to trigger lazy-loaded sections
    - Waits for client history section
    - Expands 'Jobs in progress' toggle
    - Batch-clicks ALL 'View more' review buttons (up to 150 items)
    - Expands all truncated '...more' review feedback
    - Returns raw HTML for offline preservation.
    """
    for att in range(3):
        try:
            page.goto(url, timeout=30000, wait_until="domcontentloaded")
            health = check_page_health(page)
            if health == "suspended":
                raise RuntimeError("ACCOUNT SUSPENDED")
            if health in ("cloudflare", "rate_limit", "login"):
                if not wait_cf(page, timeout=20):
                    backoff(att); continue
            break
        except RuntimeError:
            raise
        except Exception:
            if att == 2: raise
            time.sleep(3)

    # Scroll down to trigger lazy elements
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7)")
    except Exception: pass

    # Wait up to 1.2s for client history / client section (AJAX)
    deadline = time.time() + 1.2
    while time.time() < deadline:
        try:
            found = page.evaluate("""() => {
                const t=(document.body?.innerText||'').toLowerCase();
                return t.includes("client's recent history") || t.includes("recent history") ||
                       t.includes("no feedback yet") || !!document.querySelector('[data-test="client-history"]');
            }""")
            if found: break
        except Exception: pass
        time.sleep(0.1)

    # Expand "Jobs in progress" toggle if present
    try:
        page.evaluate("""() => {
            const btns = [...document.querySelectorAll('button')].filter(
                b => (b.innerText||'').toLowerCase().includes('jobs in progress')
            );
            if (btns.length) btns[0].click();
        }""")
        time.sleep(0.08)
    except Exception: pass

    # Batch-click ALL "View more" buttons simultaneously
    VIEW_MORE_JS = """(() => {
        const keywords = ['view more','show more','load more','view all'];
        const btns = [...document.querySelectorAll('a, button, span[role="button"]')].filter(el => {
            const txt = (el.innerText||el.textContent||'').trim().toLowerCase();
            return keywords.some(k => txt.startsWith(k) || txt === k);
        });
        btns.forEach(b => { try { b.click(); } catch(e) {} });
        return btns.length;
    })()"""

    for _ in range(8):
        try:
            clicked = page.evaluate(VIEW_MORE_JS)
            if clicked == 0:
                break
            time.sleep(0.1)
        except Exception:
            break

    # Scroll to bottom to ensure full render
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception: pass

    # Expand ALL truncated review/feedback "...more" text buttons
    try:
        page.evaluate("""(() => {
            document.querySelectorAll('button, span[role="button"], a').forEach(b => {
                const t = (b.innerText||b.textContent||'').trim().toLowerCase();
                if (t === 'more' || t === 'show more' || t.includes('...more') || t === 'read more') {
                    try { b.click(); } catch(e) {}
                }
            });
        })()""")
    except Exception: pass

    return page.content()


# ─── Worker (Country-by-Country, Single Tab) ─────────────────────────────────

def worker(wid, port, country_list, sk):
    from playwright.sync_api import sync_playwright

    print(f"\n[{wid}] port={port} | Countries: {', '.join(country_list[:4])}... ({len(country_list)} total)", flush=True)

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}", timeout=25000)
        ctx     = browser.contexts[0]
        # Strictly use ONLY the existing single tab for Upwork (never touch other tabs like YouTube)
        upwork_pages = [p for p in ctx.pages if "upwork.com" in p.url]
        page = upwork_pages[0] if upwork_pages else ctx.new_page()
        for p in upwork_pages[1:]:
            try: p.close()
            except Exception: pass

        for c_idx, country in enumerate(country_list, 1):
            loc_param = urllib.parse.quote(country)
            base_url  = f"https://www.upwork.com/nx/search/jobs?location={loc_param}&payment_verified=1&per_page=50&sort=recency"
            print(f"\n{'='*65}\n[{wid}] ({c_idx}/{len(country_list)}) COUNTRY: {country.upper()}\n{'='*65}", flush=True)

            consec_past = 0
            consec_failed_loads = 0
            consec_empty_cards = 0
            country_done = False

            start_pn = START_PAGES.get(country, 1)
            for pn in range(start_pn, MAX_PAGES + 1):
                if country_done:
                    break

                search_url = f"{base_url}&page={pn}"
                print(f"\n[{wid}] [{country}] Page {pn}...", flush=True)

                # 1. Load search page in the SINGLE tab
                loaded = False
                for att in range(4):
                    try:
                        page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
                        if not wait_cf(page, timeout=20):
                            backoff(att); continue
                        jitter_search()
                        loaded = True; break
                    except Exception as e:
                        print(f"  [{wid}] search err att{att+1}: {e}", flush=True)
                        backoff(att)

                if not loaded:
                    consec_failed_loads += 1
                    if consec_failed_loads >= 3:
                        print(f"[{wid}] [{country}] 3 failed search loads -> next country", flush=True)
                        break
                    continue
                consec_failed_loads = 0

                # 2. Extract cards on this search page
                cards = extract_cards(page)
                print(f"  [{wid}] [{country}] Page {pn}: {len(cards)} cards", flush=True)

                if not cards:
                    consec_empty_cards += 1
                    if consec_empty_cards >= 3:
                        print(f"[{wid}] [{country}] No cards 3x -> country complete", flush=True)
                        break
                    continue
                consec_empty_cards = 0

                # 3. Filter cards
                valid_cards = []
                pg_skip = 0

                for card in cards:
                    jid  = card.get("job_id","")
                    jurl = card.get("job_url","")
                    if not jid or not jurl or "/jobs/" not in jurl: continue

                    raw_posted = card.get("posted_raw", "")
                    p_lower    = raw_posted.lower()

                    # Today's jobs (Sept 28: minute, hour, second, just now) -> skip instantly (0 navigation)
                    if any(k in p_lower for k in ("minute", "hour", "second", "just now")):
                        pg_skip += 1
                        stats[sk+"_skip"] += 1
                        continue

                    # Older than 14 days check on search card
                    m_days = re.search(r'(\d+)\s+days?\s+ago', p_lower)
                    if m_days and int(m_days.group(1)) > 15:
                        consec_past += 1
                        if consec_past >= 10:
                            country_done = True
                            print(f"[{wid}] [{country}] 10 cards older than 14 days -> country complete!", flush=True)
                            break
                        continue

                    # MUTEX CLAIM: check if already claimed or already in DB
                    with claimed_lock:
                        if jid in claimed_ids:
                            pg_skip += 1
                            stats[sk+"_skip"] += 1
                            continue
                        claimed_ids.add(jid)

                    valid_cards.append(card)

                if country_done:
                    break

                if not valid_cards:
                    print(f"  [{wid}] [{country}] Page {pn}: all {len(cards)} cards skipped (today or already saved)", flush=True)
                    continue

                # 4. Fetch details in the SAME SINGLE TAB
                for card in valid_cards:
                    jid   = card.get("job_id","")
                    jurl  = card.get("job_url","")
                    title = card.get("job_title","")[:45]

                    for att in range(2):
                        try:
                            raw_html = fetch_full_detail(page, jurl)
                            job_obj  = parse_job_detail_page(raw_html, job_url=jurl, search_card_metadata=card)
                            job_dict = job_obj.model_dump(mode="json")
                            if card.get("job_title"): job_dict["job_title"] = card["job_title"]

                            actual_dt = _date(job_dict)

                            # Enforce 14-day boundary on detail page
                            if actual_dt and actual_dt > DATE_END:
                                print(f"  [{wid}] SKIP (Newer than {DATE_END}): {actual_dt}", flush=True)
                                break
                            if actual_dt and actual_dt < DATE_START:
                                print(f"  [{wid}] SKIP (Older than {DATE_START}): {actual_dt}", flush=True)
                                consec_past += 1
                                if consec_past >= 8:
                                    country_done = True
                                    print(f"[{wid}] [{country}] Reached jobs older than {DATE_START} ({actual_dt}) -> country complete!", flush=True)
                                break
                            consec_past = 0

                            hist = len(job_dict.get("client_recent_history") or [])
                            save_job(job_dict, jid, raw_html)
                            cur_rate = record_save(wid)
                            with db_lock:
                                stats[sk+"_new"] += 1

                            a = stats["a_new"]
                            b = stats["b_new"]
                            print(f"  [{wid}] [{country}] SAVED #{stats[sk+'_new']} {title!r} | "
                                  f"{cur_rate}/min | hist:{hist} | {actual_dt} | total:{a+b}", flush=True)
                            jitter_detail()
                            break
                        except Exception as e:
                            if att == 0:
                                print(f"    [{wid}] retry {jid}: {e}", flush=True)
                                time.sleep(3)
                            else:
                                with claimed_lock:
                                    claimed_ids.discard(jid)
                                stats["errors"] += 1
                                print(f"    [{wid}] ERR {jid}: {e}", flush=True)

                    if country_done:
                        break

            print(f"\n[{wid}] Finished country: {country}! Total new for {wid}: {stats[sk+'_new']}", flush=True)

    print(f"\n[{wid}] ALL COUNTRIES COMPLETE: {stats[sk+'_new']} new jobs fetched", flush=True)


# ─── Main Orchestrator ────────────────────────────────────────────────────────

def main():
    start = time.time()
    print("="*70, flush=True)
    print("  FLODATA 14-DAY DUAL SCRAPER v6 (Country-by-Country, Single Tab)", flush=True)
    print(f"  Window: {DATE_START} -> {DATE_END}", flush=True)
    print(f"  Port {PORT_A} (Chrome): {len(COUNTRIES_A)} Western/English Countries", flush=True)
    print(f"  Port {PORT_B} (Edge):   {len(COUNTRIES_B)} Europe/Asia/ME Countries (resuming: Switzerland)", flush=True)
    print(f"  Tab Policy: STRICTLY 1 TAB per browser (Zero multi-tab clutter)", flush=True)
    print(f"  Mutual Atomic Claim: Active (0% duplicate jobs)", flush=True)
    print("="*70, flush=True)
    for port, name in [(PORT_A,"Chrome-A"),(PORT_B,"Edge-B")]:
        try:
            info = json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=4).read())
            print(f"  [OK] Port {port} ({name}): {info.get('Browser','?')}", flush=True)
        except Exception:
            print(f"  [!!] Port {port} ({name}): NOT REACHABLE!", flush=True); return

    setup_db()


    ta = threading.Thread(
        target=worker,
        args=("A", PORT_A, COUNTRIES_A, "a"),
        daemon=True, name="Worker-A"
    )
    tb = threading.Thread(
        target=worker,
        args=("B", PORT_B, COUNTRIES_B, "b"),
        daemon=True, name="Worker-B"
    )

    print(f"\n  Launching both workers simultaneously in 1 tab each...\n", flush=True)
    ta.start()
    time.sleep(1.5)
    tb.start()

    last_report = time.time()

    while ta.is_alive() or tb.is_alive():
        time.sleep(25)
        now = time.time()
        if now - last_report >= 50:
            elapsed = int(now - start)
            try: total_db = sqlite3.connect(DB_14DAYS, timeout=5).execute(
                    "SELECT COUNT(*) FROM jobs").fetchone()[0]
            except Exception: total_db = "?"
            a = stats["a_new"]
            b = stats["b_new"]
            rate = (a+b) / max(elapsed/60, 0.1)
            print(f"\n[Progress] {elapsed//60}m{elapsed%60:02d}s | "
                  f"A:{a} B:{b} total:{a+b} | {rate:.1f}/min (A:{a/max(elapsed/60,0.1):.1f}/min, B:{b/max(elapsed/60,0.1):.1f}/min) | "
                  f"errors:{stats['errors']} | DB:{total_db:,}", flush=True)
            last_report = now

    ta.join()
    tb.join()

    elapsed = int(time.time() - start)
    total_db = sqlite3.connect(DB_14DAYS).execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    a = stats["a_new"]
    b = stats["b_new"]

    print("\n"+"="*70, flush=True)
    print(f"  COMPLETE in {elapsed//60}m {elapsed%60}s", flush=True)
    print(f"  Worker A: {a} new", flush=True)
    print(f"  Worker B: {b} new", flush=True)
    print(f"  Total new: {a+b}", flush=True)
    print(f"  Final DB:  {total_db:,}", flush=True)
    print("="*70, flush=True)


if __name__ == "__main__":
    main()
