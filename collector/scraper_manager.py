"""
FLODATA DUAL-BROWSER SCRAPER MANAGER
====================================
Orchestrates Worker A (Chrome: Port 9222) and Worker B (Edge: Port 9223)
with dynamic date ranges, auto-browser boot, and live telemetry streaming.
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
from typing import Dict, Any, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from generate_standalone_report import clean_freelancer_review, generate_report
from collector.storage.central import CentralStore, database_path
from collector.extraction.job_parser import parse_job_detail_page

OUTPUT_DIR = ROOT / "output"
LOGS_DIR = OUTPUT_DIR / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DB_14DAYS = database_path(OUTPUT_DIR)
DB_MAIN   = database_path(OUTPUT_DIR)
DB_1WEEK  = database_path(OUTPUT_DIR)

PORT_A = 9222  # Chrome
PORT_B = 9223  # Edge

ALL_TARGET_COUNTRIES = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia and New Zealand",
    "Europe",
    "India",
    "United Arab Emirates",
    "Saudi Arabia",
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
    "United States Virgin Islands"
]


class ScraperManager:
    def __init__(self):
        self.lock = threading.Lock()
        self.db_lock = threading.Lock()
        self.stop_event = threading.Event()
        self.is_running = False
        
        self.date_start = "2026-09-28"
        self.date_end = "2026-10-04"
        self.countries = list(ALL_TARGET_COUNTRIES)
        
        self.country_queue = Queue()
        self.claimed_ids = set()
        
        self.stats = {
            "a_new": 0, "b_new": 0,
            "a_skip": 0, "b_skip": 0,
            "errors": 0,
            "sweep": 1
        }
        
        self.worker_a_status = {
            "online": False,
            "country": "Idle",
            "page": 0,
            "action": "Standing by",
            "saved": 0,
            "skips": 0
        }
        
        self.worker_b_status = {
            "online": False,
            "country": "Idle",
            "page": 0,
            "action": "Standing by",
            "saved": 0,
            "skips": 0
        }
        
        self.start_time = None
        self.recent_saves_a = deque()
        self.recent_saves_b = deque()
        self.logs_stream = deque(maxlen=100)
        
        self.worker_a_thread = None
        self.worker_b_thread = None
        self.reporter_thread = None

    def log(self, msg: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {msg}"
        self.logs_stream.append(line)
        print(line, flush=True)

    @staticmethod
    def is_port_ready(port: int) -> bool:
        for host in ["localhost", "127.0.0.1"]:
            try:
                with urllib.request.urlopen(f"http://{host}:{port}/json/version", timeout=0.8) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
        return False

    def _update_tab_hud(self, page, wid: str, country: str, pn: int, action: str, saved: int):
        """Ensures the browser tab and web page visibly display 'WORKING' status."""
        try:
            page.evaluate("""({wid, country, pn, action, saved}) => {
                try {
                    // Update visible browser tab title
                    document.title = `[WORKING ⚡] Upwork Scraper (${wid}) - ${country || 'Global'} P${pn || 1}`;

                    // Inject or update prominent floating HUD on page
                    let hud = document.getElementById('flodata-live-hud');
                    if (!hud) {
                        hud = document.createElement('div');
                        hud.id = 'flodata-live-hud';
                        hud.style.position = 'fixed';
                        hud.style.top = '14px';
                        hud.style.right = '16px';
                        hud.style.zIndex = '99999999';
                        hud.style.background = 'linear-gradient(135deg, rgba(15, 23, 42, 0.96), rgba(8, 12, 22, 0.96))';
                        hud.style.border = '2px solid #10b981';
                        hud.style.borderRadius = '12px';
                        hud.style.padding = '10px 16px';
                        hud.style.boxShadow = '0 10px 30px rgba(0, 0, 0, 0.85), 0 0 20px rgba(16, 185, 129, 0.35)';
                        hud.style.fontFamily = 'system-ui, -apple-system, sans-serif';
                        hud.style.color = '#f8fafc';
                        hud.style.display = 'flex';
                        hud.style.alignItems = 'center';
                        hud.style.gap = '12px';
                        hud.style.pointerEvents = 'none';
                        hud.style.transition = 'all 0.25s ease';
                        document.body.appendChild(hud);
                    }
                    hud.innerHTML = `
                        <div style="width: 12px; height: 12px; border-radius: 50%; background: #10b981; box-shadow: 0 0 10px #10b981; flex-shrink: 0; animation: pulse 1.5s infinite;"></div>
                        <div>
                            <div style="font-weight: 800; font-size: 13px; color: #10b981; letter-spacing: 0.5px;">
                                ⚡ WORKER ${wid}: WORKING
                            </div>
                            <div style="font-size: 11px; color: #cbd5e1; margin-top: 2px;">
                                📍 <b>${country || 'Ready'}</b> (P${pn || 1}) • 💾 Saved: <b style="color: #38bdf8;">${saved || 0}</b>
                            </div>
                            <div style="font-size: 10px; color: #94a3b8; margin-top: 2px; max-width: 260px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                                ${action || 'Active'}
                            </div>
                        </div>
                    `;
                } catch(e) {}
            }""", {"wid": wid, "country": country, "pn": pn, "action": action, "saved": saved})
        except Exception:
            pass

    def ensure_browsers_running(self) -> Dict[str, bool]:
        """Automatically checks and launches Chrome (9222) and Edge (9223) in visible mode."""
        chrome_ok = self.is_port_ready(PORT_A)
        edge_ok = self.is_port_ready(PORT_B)

        chrome_prof = os.path.expandvars(r"%USERPROFILE%\chrome_upwork_profile")
        edge_prof = os.path.expandvars(r"%USERPROFILE%\edge_upwork_profile")

        chrome_exe = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
        if not Path(chrome_exe).exists():
            chrome_exe = r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"

        edge_exe = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
        if not Path(edge_exe).exists():
            edge_exe = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"

        if not chrome_ok or not edge_ok:
            self.log("🚀 Launching interactive Chrome & Edge windows onto your desktop screen...")
            try:
                subprocess.Popen(["schtasks", "/run", "/tn", "FlodataLaunchTabs"], shell=False)
            except Exception:
                pass
            try:
                subprocess.Popen(["explorer.exe", r"C:\Users\princ\Desktop\open_both_browsers.bat"], shell=False)
            except Exception:
                pass

        # Wait up to 6 seconds for ports to become alive
        deadline = time.time() + 6
        while time.time() < deadline:
            if not chrome_ok:
                chrome_ok = self.is_port_ready(PORT_A)
            if not edge_ok:
                edge_ok = self.is_port_ready(PORT_B)
            if chrome_ok and edge_ok:
                break
            time.sleep(0.5)

        # Bring browser tabs to front and update HUD
        for port, wid, ok in [(PORT_A, "A", chrome_ok), (PORT_B, "B", edge_ok)]:
            if ok:
                try:
                    from playwright.sync_api import sync_playwright
                    with sync_playwright() as pw:
                        b = pw.chromium.connect_over_cdp(f"http://localhost:{port}", timeout=3500)
                        ctx = b.contexts[0]
                        for p in list(ctx.pages):
                            if "cloudflare" in p.url.lower():
                                try: p.close()
                                except Exception: pass
                        upwork_pages = [p for p in ctx.pages if "upwork.com" in p.url]
                        if "login" in target_page.url.lower() or "account-security" in target_page.url.lower() or "just a moment" in (target_page.title() or "").lower():
                            try:
                                target_page.goto("https://www.upwork.com/login", timeout=15000, wait_until="commit")
                            except Exception:
                                pass
                        target_page.bring_to_front()
                        self._update_tab_hud(target_page, wid, "Standby", 1, "Ready for manual login", 0)
                except Exception:
                    pass

        self.worker_a_status["online"] = chrome_ok
        self.worker_b_status["online"] = edge_ok
        return {"chrome_port_9222": chrome_ok, "edge_port_9223": edge_ok}

    def setup_databases(self):
        self.store = CentralStore(DB_MAIN)
        self.store.initialize()
        self.store.migrate_legacy(OUTPUT_DIR)
        if getattr(self, "run_id", None):
            self.store.finish_run(self.run_id, "window_changed")
        self.run_id = self.store.start_run(self.date_start, self.date_end)
        self.claimed_ids = self.store.ids(self.date_start, self.date_end)
        self.log(f"Central database: {DB_MAIN.name}; {len(self.claimed_ids):,} jobs in selected window")

    def save_job(self, job_dict: dict, jid: str, raw_html: str, actual_dt: str):
        data = {k: v for k, v in job_dict.items() if k != "raw_html"}
        with self.db_lock:
            self.store.save(jid, data, raw_html, self.run_id)

    def extract_job_date(self, d: dict) -> str:
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

    def _worker_stream(self, wid: str, port: int):
        from playwright.sync_api import sync_playwright

        status_dict = self.worker_a_status if wid == "A" else self.worker_b_status
        sk = "a" if wid == "A" else "b"
        status_dict["online"] = True
        status_dict["action"] = f"Connecting to Port {port}..."

        self.log(f"[Worker {wid}] Connecting to Port {port} over CDP...")

        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(f"http://localhost:{port}", timeout=30000)
                ctx = browser.contexts[0]
                for p in list(ctx.pages):
                    if "cloudflare" in p.url.lower():
                        try: p.close()
                        except Exception: pass
                upwork_pages = [p for p in ctx.pages if "upwork.com" in p.url]
                if "login" in page.url.lower() or "account-security" in page.url.lower() or "just a moment" in (page.title() or "").lower():
                    try:
                        page.goto("https://www.upwork.com/login", timeout=15000, wait_until="commit")
                    except Exception:
                        pass
                    page.bring_to_front()
                    self.log(f"[Worker {wid}] ⚠️ Manual Upwork login / verification required on Port {port}. Please log in in the browser window...")
                    while not self.stop_event.is_set():
                        time.sleep(3)
                        try:
                            c_url = (page.url or "").lower()
                            c_tit = (page.title() or "").lower()
                            if "login" not in c_url and "account-security" not in c_url and "just a moment" not in c_tit:
                                self.log(f"[Worker {wid}] ✅ Login detected! Starting scraper stream.")
                                break
                        except Exception:
                            pass

                try:
                    page.bring_to_front()
                except Exception:
                    pass

                self.log(f"✅ [Worker {wid}] Connected! Browser tab is visible and active.")

                while not self.stop_event.is_set():
                    # Handle queue replenishment & sweeping
                    with self.lock:
                        if self.country_queue.empty():
                            self.stats["sweep"] += 1
                            self.log(f"🔄 [Sweeper] Sweep #{self.stats['sweep']} starting across all {len(self.countries)} countries!")
                            for c in self.countries:
                                self.country_queue.put(c)
                            time.sleep(2)

                    try:
                        country = self.country_queue.get(timeout=3)
                    except Empty:
                        time.sleep(1)
                        continue

                    status_dict["country"] = country
                    encoded_country = urllib.parse.quote(country)
                    base_url = f"https://www.upwork.com/nx/search/jobs?location={encoded_country}&payment_verified=1&per_page=50&sort=recency"

                    self.log(f"🌐 [Worker {wid}] Starting Country: {country.upper()} (Target: {self.date_start} to {self.date_end})")
                    consec_past = 0

                    for pn in range(1, 51):
                        if self.stop_event.is_set():
                            break

                        status_dict["page"] = pn
                        status_dict["action"] = f"Loading {country} Page {pn}"
                        search_url = f"{base_url}&page={pn}"

                        try:
                            page.goto(search_url, timeout=40000, wait_until="domcontentloaded")
                            time.sleep(random.uniform(2.0, 3.0))
                            self._update_tab_hud(page, wid, country, pn, f"Searching {country} (Page {pn})", status_dict["saved"])
                        except Exception as e:
                            self.log(f"⚠️ [Worker {wid}] Page {pn} navigation: {e}")
                            time.sleep(2)
                            continue

                        # Rate-limit & Login Redirect Auto-Protection
                        cur_url = (page.url or "").lower()
                        cur_title = (page.title() or "").lower()
                        if "account-security" in cur_url or "login" in cur_url or "1015" in cur_title or "rate limit" in cur_title or "access denied" in cur_title:
                            self.log(f"⚠️ [Worker {wid}] Notice: Login/Rate-limit verification detected on {country}. Auto-recovering to clean search page...")
                            status_dict["action"] = "Auto-recovering to Search..."
                            try:
                                page.goto("https://www.upwork.com/nx/search/jobs?sort=recency", timeout=25000)
                                time.sleep(3.0)
                            except Exception:
                                pass
                            break

                        # Extract cards directly from DOM
                        try:
                            cards = page.evaluate("""() => {
                                const jobs = [];
                                const arts = [...document.querySelectorAll('article, li[data-test], [data-test="job-tile"]')];
                                for (const a of arts) {
                                    const link = a.querySelector('a[href*="/jobs/"]');
                                    if (!link) continue;
                                    const href = link.href || '';
                                    const m = href.match(/~([0-9a-f]+)/i);
                                    if (!m) continue;
                                    const id = '~' + m[1];
                                    const titleEl = a.querySelector('[data-test="job-tile-title"], h2, h3, h4');
                                    const title = titleEl ? titleEl.innerText.trim() : '';
                                    const postedEl = a.querySelector('[data-test="posted-on"], [class*="posted"], time, small');
                                    const posted_raw = postedEl ? postedEl.innerText.trim() : '';
                                    const locEl = a.querySelector('[data-test="client-country"], [class*="client-location"]');
                                    const location = locEl ? locEl.innerText.trim() : '';
                                    jobs.push({
                                        job_id: id,
                                        job_url: href.split('?')[0],
                                        job_title: title,
                                        posted_raw: posted_raw,
                                        client_location: location
                                    });
                                }
                                return jobs;
                            }""")
                        except Exception:
                            cards = []

                        if not cards:
                            time.sleep(1.5)
                            continue

                        country_cutoff = False

                        for card in cards:
                            if self.stop_event.is_set():
                                break

                            jid = card.get("job_id", "")
                            jurl = card.get("job_url", "")
                            title = card.get("job_title", "")
                            posted_raw = card.get("posted_raw", "")
                            p_lower = posted_raw.lower()

                            # 0ms Fast Card Pre-Filter: If posted minutes or <= 16 hours ago, it's newer than window
                            m_hours = re.search(r'(\d+)\s+hours?\s+ago', p_lower)
                            if ("minute" in p_lower or "second" in p_lower or "just now" in p_lower or (m_hours and int(m_hours.group(1)) <= 16)):
                                status_dict["skips"] += 1
                                continue

                            # Cutoff check: If relative date is 8+ days ago, we are past the lower bound
                            m_days = re.search(r'(\d+)\s+days?\s+ago', p_lower)
                            if m_days and int(m_days.group(1)) >= 8:
                                consec_past += 1
                                if consec_past >= 6:
                                    self.log(f"🏁 [Worker {wid}] [{country}] 6 consecutive jobs older than {self.date_start} -> Country complete!")
                                    country_cutoff = True
                                    break
                                continue

                            # Atomic claim
                            with self.lock:
                                if jid in self.claimed_ids:
                                    status_dict["skips"] += 1
                                    continue
                                self.claimed_ids.add(jid)

                            # Fetch full detail in visible tab
                            try:
                                status_dict["action"] = f"Extracting: {title[:28]}"
                                page.goto(jurl, timeout=35000, wait_until="domcontentloaded")
                                time.sleep(1.0)
                                self._update_tab_hud(page, wid, country, pn, f"Extracting: {title[:28]}", status_dict["saved"])

                                # Expand view more
                                try:
                                    page.evaluate("""(() => {
                                        const keywords = ['view more', 'show more', 'load more'];
                                        [...document.querySelectorAll('a, button, span[role="button"]')].forEach(el => {
                                            const t = (el.innerText || '').trim().toLowerCase();
                                            if (keywords.some(k => t.startsWith(k))) el.click();
                                        });
                                    })()""")
                                except Exception:
                                    pass

                                raw_html = page.content()
                                job_obj = parse_job_detail_page(raw_html, job_url=jurl, search_card_metadata=card)
                                job_dict = job_obj.model_dump(mode="json")
                                if title:
                                    job_dict["job_title"] = title

                                actual_dt = self.extract_job_date(job_dict)

                                # Date Bounds Check
                                if actual_dt and actual_dt > self.date_end:
                                    status_dict["skips"] += 1
                                    continue
                                if actual_dt and actual_dt < self.date_start:
                                    consec_past += 1
                                    status_dict["skips"] += 1
                                    if consec_past >= 6:
                                        self.log(f"🏁 [Worker {wid}] [{country}] Reached end of window ({actual_dt}) -> Country complete!")
                                        country_cutoff = True
                                        break
                                    continue

                                consec_past = 0

                                # Clean freelancer reviews
                                clean_revs = []
                                for h in (job_dict.get("client_recent_history") or []):
                                    fb = clean_freelancer_review(h.get("feedback"), h.get("freelancer_name"))
                                    if fb:
                                        h["feedback"] = fb
                                        clean_revs.append(h)
                                job_dict["client_recent_history"] = clean_revs

                                self.save_job(job_dict, jid, raw_html, actual_dt)
                                status_dict["saved"] += 1
                                self.stats[sk + "_new"] += 1
                                self._update_tab_hud(page, wid, country, pn, f"Saved: {title[:28]}", status_dict["saved"])

                                total_saved = self.stats["a_new"] + self.stats["b_new"]
                                self.log(f"💾 [Worker {wid}] [{country}] Saved #{status_dict['saved']} (Total: {total_saved}) '{title[:28]}' | {actual_dt or posted_raw}")

                                # Pacing sleep
                                time.sleep(random.uniform(1.4, 2.0))

                            except Exception as e:
                                self.log(f"⚠️ [Worker {wid}] Detail err on {jid}: {e}")
                                time.sleep(1.5)
                                time.sleep(1.5)

                        if country_cutoff:
                            break

        except Exception as e:
            self.log(f"❌ [Worker {wid}] Fatal connection error: {e}")
        finally:
            status_dict["online"] = False
            status_dict["action"] = "Stopped"

    def _periodic_reporter(self):
        """Auto-rebuilds the HTML report every 3 minutes while running."""
        while not self.stop_event.is_set():
            time.sleep(180)
            if self.stats["a_new"] + self.stats["b_new"] > 0:
                try:
                    self.log("📊 [Report Auto-Sync] Generating date-filtered HTML report from the permanent database...")
                    generate_report(
                        db_path=str(DB_1WEEK),
                        output_html=str(OUTPUT_DIR / "upwork_1week_report.html"),
                        date_filter_start=self.date_start,
                        date_filter_end=self.date_end,
                        report_title=f"Upwork Market Intelligence Hub — Verified Jobs ({self.date_start} to {self.date_end})"
                    )
                    # Sync to root
                    import shutil
                    shutil.copyfile(str(OUTPUT_DIR / "upwork_1week_report.html"), str(ROOT / f"upwork_1week_{self.date_start}_to_{self.date_end}.html"))
                    shutil.copyfile(str(OUTPUT_DIR / "upwork_1week_report.html"), str(ROOT / "upwork_1week_report.html"))
                    self.log("✅ [Report Auto-Sync] HTML reports synchronized.")
                except Exception as e:
                    self.log(f"⚠️ Report sync notice: {e}")

    def start_scrape(self, start_date: str, end_date: str, countries: Optional[List[str]] = None) -> Dict[str, Any]:
        with self.lock:
            if self.is_running:
                return {"status": "already_running", "message": "Scraper is already active"}

            self.date_start = start_date.strip()
            self.date_end = end_date.strip()
            self.countries = [c.strip() for c in (countries or ALL_TARGET_COUNTRIES) if c.strip()]
            self.stop_event.clear()
            self.is_running = True
            self.start_time = time.time()

            # Empty queue and repopulate
            while not self.country_queue.empty():
                try:
                    self.country_queue.get_nowait()
                except Empty:
                    break
            for c in self.countries:
                self.country_queue.put(c)

            self.setup_databases()

        self.log(f"🚀 INITIATING DUAL SCRAPER ENGINE (Window: {self.date_start} to {self.date_end} | Countries: {len(self.countries)})")

        # 1. Ensure both browsers are alive
        browsers_status = self.ensure_browsers_running()

        # 2. Start Worker threads
        self.worker_a_thread = threading.Thread(target=self._worker_stream, args=("A", PORT_A), daemon=True)
        self.worker_a_thread.start()

        self.worker_b_thread = threading.Thread(target=self._worker_stream, args=("B", PORT_B), daemon=True)
        self.worker_b_thread.start()

        self.reporter_thread = threading.Thread(target=self._periodic_reporter, daemon=True)
        self.reporter_thread.start()

        return {
            "status": "started",
            "start_date": self.date_start,
            "end_date": self.date_end,
            "countries_count": len(self.countries),
            "browsers": browsers_status
        }

    def stop_scrape(self) -> Dict[str, Any]:
        with self.lock:
            if not self.is_running:
                return {"status": "not_running", "message": "Scraper is not running"}
            self.stop_event.set()
            if getattr(self, "run_id", None):
                self.store.finish_run(self.run_id, "stopped")
            self.is_running = False
            self.log("⏹️ Stop requested. Gracefully pausing active workers...")

        return {"status": "stopping", "message": "Scraper is stopping gracefully."}

    def get_telemetry(self) -> Dict[str, Any]:
        now = time.time()
        elapsed = int(now - self.start_time) if self.start_time and self.is_running else 0
        total_saved = self.stats["a_new"] + self.stats["b_new"]
        rate = round((total_saved / (elapsed / 60.0)), 1) if elapsed > 30 else 0.0

        return {
            "is_running": self.is_running,
            "date_start": self.date_start,
            "date_end": self.date_end,
            "total_saved": total_saved,
            "rate_per_min": rate,
            "elapsed_seconds": elapsed,
            "sweep": self.stats["sweep"],
            "worker_a": {
                "port": PORT_A,
                "browser": "Google Chrome",
                "online": self.worker_a_status["online"],
                "country": self.worker_a_status["country"],
                "page": self.worker_a_status["page"],
                "action": self.worker_a_status["action"],
                "saved": self.worker_a_status["saved"],
                "skips": self.worker_a_status["skips"]
            },
            "worker_b": {
                "port": PORT_B,
                "browser": "Microsoft Edge",
                "online": self.worker_b_status["online"],
                "country": self.worker_b_status["country"],
                "page": self.worker_b_status["page"],
                "action": self.worker_b_status["action"],
                "saved": self.worker_b_status["saved"],
                "skips": self.worker_b_status["skips"]
            },
            "recent_logs": list(self.logs_stream)
        }


# Global Singleton Manager
scraper_manager = ScraperManager()
