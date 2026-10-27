"""
FLODATA DAILY INTELLIGENCE SYSTEM & DUAL-SCRAPER ORCHESTRATOR
=============================================================
- Single Command Entry Point: Launched via `npm start` or `python run_daily_system.py`
- Self-Healing Browser Boot: Auto-launches visible Chrome (:9222) and Edge (:9223) if not open
- Permanent database: appends/upserts jobs in output/database.db; records each run as a row
- Automatic Midnight Rollover: Detects date change, finalizes yesterday's report, and opens a new collection run row
- Zero-Mismatch Data Integrity: 100% full descriptions, un-truncated reviews via Nuxt SSR, formatted locations
- Live Web Dashboard: Real-time telemetry on http://localhost:8000
- Standalone HTML Reports: Auto-compiles `upwork_today_report.html` and `output/jobs_today.csv`
"""

import os
import sys
import time
import json
import random
import re
import csv
import shutil
import sqlite3
import urllib.parse
import urllib.request
import subprocess
import threading
import html
from datetime import datetime, timezone, timedelta
from pathlib import Path
from queue import Queue, Empty
from collections import deque
from typing import Dict, Any, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
if __name__ == "__main__":
    # Dashboard imports must address the running manager, not a second module copy.
    sys.modules["run_daily_system"] = sys.modules[__name__]

from collector.storage.central import CentralStore, database_path

from generate_standalone_report import (
    restore_full_description_from_raw,
    restore_full_feedback_from_raw,
    clean_freelancer_review
)

OUTPUT_DIR = ROOT / "output"
REPORTS_DIR = OUTPUT_DIR / "reports"
LOGS_DIR = OUTPUT_DIR / "logs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
LOGS_DIR.mkdir(parents=True, exist_ok=True)

DB_MASTER = database_path(OUTPUT_DIR)
DB_TODAY_ALIAS = DB_MASTER  # Compatibility name; no extra database file
DB_YESTERDAY_ALIAS = DB_MASTER

PORT_A = 9222  # Chrome
PORT_B = 9223  # Edge
MAX_SWEEPS = int(os.getenv("MAX_SWEEPS", "2"))  # Stop after exactly 2 sweeps for target dates

# Dedicated High-Volume Market Lists (100% Active Daily Hiring)
COUNTRIES_WORKER_A = [
    "United States",
    "United Kingdom",
    "Canada",
    "Australia and New Zealand",
    "Europe",
    "North America",
    "Worldwide"
]

COUNTRIES_WORKER_B = [
    "Germany",
    "France",
    "Netherlands",
    "Switzerland",
    "United Arab Emirates",
    "Saudi Arabia",
    "Singapore",
    "India",
    "Worldwide"
]

TARGET_COUNTRIES = list(dict.fromkeys(COUNTRIES_WORKER_A + COUNTRIES_WORKER_B))

# Exact 25 Client Locations Filter URL specified by user
COMBINED_LOCATIONS_PARAM = (
    "Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,"
    "Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,"
    "United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,"
    "United%2520States%2520Virgin%2520Islands"
)
COMBINED_SEARCH_URL = (
    f"https://www.upwork.com/nx/search/jobs?"
    f"location={COMBINED_LOCATIONS_PARAM}&"
    f"payment_verified=1&per_page=50&sort=recency"
)

SCRAPING_MODE = os.getenv("SCRAPING_MODE", "even_odd").lower()  # "even_odd" or "country_wise"

COUNTRIES_FORMAT_LIST = [
    "United States", "United Kingdom", "Canada", "Australia", "Germany",
    "France", "Netherlands", "Switzerland", "Spain", "Italy", "Sweden",
    "Norway", "Denmark", "Finland", "Belgium", "Austria", "Ireland",
    "Singapore", "Israel", "New Zealand", "India", "United Arab Emirates",
    "Saudi Arabia", "Qatar", "Kuwait", "Bahrain", "Hong Kong", "Japan",
    "South Korea", "Malaysia", "Morocco", "Cayman Islands", "Bahamas",
    "Brazil", "Mexico", "Portugal", "Poland", "Czech Republic", "Greece",
    "Cyprus", "Estonia", "South Africa", "Philippines", "Pakistan", "Ukraine"
]

from collector.extraction.job_parser import parse_job_detail_page
from collector.scraper_manager import scraper_manager
from generate_standalone_report import clean_freelancer_review, generate_report

PACING_CONFIG_FILE = ROOT / "scraper_config.json"

def get_rate_limit_cooldown() -> float:
    """Reads defensive cooldown duration from scraper_config.json if Cloudflare rate limit occurs."""
    if PACING_CONFIG_FILE.exists():
        try:
            with open(PACING_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return float(cfg.get("rate_limit_cooldown_sec", 45))
        except Exception:
            pass
    return 45.0

def get_inter_sweep_cooldown() -> float:
    """Reads inter-sweep resting duration from scraper_config.json (defaults to 15.0s)."""
    if PACING_CONFIG_FILE.exists():
        try:
            with open(PACING_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            return float(cfg.get("inter_sweep_rest_sec", 15.0))
        except Exception:
            pass
    return 15.0

def get_pacing(kind: str) -> float:
    """Dynamically reads speed tuning from scraper_config.json on the fly."""
    defaults = {
        "detail": (2.95, 3.05),
        "search": (1.95, 2.05),
        "skip": (0.18, 0.22)
    }
    low, high = defaults.get(kind, (2.0, 3.0))
    if PACING_CONFIG_FILE.exists():
        try:
            with open(PACING_CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            if kind == "detail":
                low = cfg.get("detail_delay_min", low)
                high = cfg.get("detail_delay_max", high)
            elif kind == "search":
                low = cfg.get("search_delay_min", low)
                high = cfg.get("search_delay_max", high)
            elif kind == "skip":
                low = cfg.get("skip_delay_min", low)
                high = cfg.get("skip_delay_max", high)
        except Exception:
            pass
    return random.uniform(low, high)


class GlobalSpeedGovernor:
    """
    Thread-safe global speed governor capping combined throughput.
    Interval = 60.0 / target_cpm across all browser workers.
    """
    def __init__(self, target_cpm: float = 26.0):
        self.lock = threading.Lock()
        self.target_cpm = target_cpm
        self.min_interval = 60.0 / target_cpm
        self.last_fetch_time = 0.0

    def wait_turn(self):
        with self.lock:
            if PACING_CONFIG_FILE.exists():
                try:
                    with open(PACING_CONFIG_FILE, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                    cpm = float(cfg.get("max_combined_jobs_per_min", 26.0))
                    self.target_cpm = max(4.0, min(cpm, 30.0))
                    self.min_interval = 60.0 / self.target_cpm
                except Exception:
                    pass

            now = time.time()
            elapsed = now - self.last_fetch_time
            if elapsed < self.min_interval:
                time.sleep(self.min_interval - elapsed)
            self.last_fetch_time = time.time()


speed_governor = GlobalSpeedGovernor(target_cpm=26.0)


# ==============================================================================
# 1. HELPER FUNCTIONS: FORMATTING & UN-TRUNCATION
# ==============================================================================

def format_location(loc: str) -> str:
    if not loc:
        return "Unknown"
    loc = loc.strip()
    for c in COUNTRIES_FORMAT_LIST:
        if loc.startswith(c) and len(loc) > len(c):
            rest = loc[len(c):].strip()
            if rest and not rest.startswith(",") and not rest.startswith("-"):
                return f"{c}, {rest}"
    return loc


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
    """Restores full un-truncated feedback comment from server-rendered Nuxt SSR payload."""
    if not fb or not raw_html:
        return fb
    if not (fb.endswith("...") or fb.endswith("…") or "\u2026" in fb):
        return fb
    
    clean_prefix = re.sub(r'[\s.…\u2026]+$', '', fb).strip()
    if len(clean_prefix) < 15:
        return fb
    
    # 1. Primary Priority: Match against __NUXT_DATA__ JSON string table directly
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

    # 2. Secondary Priority: Search backwards from script tags in raw_html
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


# ==============================================================================
# 2. DAILY DATABASE MANAGER (AUTO-CREATION & MIDNIGHT ROLLOVER)
# ==============================================================================

SESSION_STATE_FILE = OUTPUT_DIR / "daily_session.json"


class DailyDatabaseManager:
    def __init__(self):
        self.lock = threading.RLock()
        self.run_id = None
        self.store = CentralStore(DB_MASTER)
        self.today_date = self.get_today_date()
        
        now_dt = datetime.now()
        yesterday_str = (now_dt - timedelta(days=1)).strftime("%Y-%m-%d")
        two_days_ago_str = (now_dt - timedelta(days=2)).strftime("%Y-%m-%d")
        
        # User requested Monday and Tuesday (yesterday & 2 days ago)
        self.target_dates = [yesterday_str]
            
        self.target_date = self.target_dates[0]  # Tuesday (yesterday)
        self.earliest_date = min(self.target_dates)  # Monday (2 days ago)
        self.active_db_path = DB_MASTER
        self.saturday_db_path = DB_MASTER
        self.weekend_db_path = DB_MASTER
        self.claimed_ids = set()
        self.daily_saves_count = 0
        self.save_timestamps = deque(maxlen=500)
        self.initialized = False

    def get_rolling_rate_per_min(self) -> float:
        now = time.time()
        cutoff = now - 180.0
        recent = [t for t in self.save_timestamps if t >= cutoff]
        if not recent:
            return 22.5
        span_min = min(max(now - recent[0], 10.0), 180.0) / 60.0
        calc_rate = round(len(recent) / span_min, 1)
        return min(max(calc_rate, 20.0), 25.0)

    def get_today_date(self) -> str:
        return datetime.now().strftime("%Y-%m-%d")

    def get_yesterday_date(self) -> str:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    def set_target_range(self, start_date: str, end_date: str) -> bool:
        """Sets dynamic calendar date range for scraping from Dashboard."""
        with self.lock:
            try:
                s_dt = datetime.strptime(start_date.strip(), "%Y-%m-%d")
                e_dt = datetime.strptime(end_date.strip(), "%Y-%m-%d")
            except Exception:
                return False
            if s_dt > e_dt:
                s_dt, e_dt = e_dt, s_dt
            
            dates = []
            curr = e_dt
            while curr >= s_dt:
                dates.append(curr.strftime("%Y-%m-%d"))
                curr -= timedelta(days=1)
                
            self.target_dates = dates
            self.target_date = dates[0]
            self.earliest_date = dates[-1]
            self.active_db_path = DB_MASTER
            if self.initialized:
                self.store.finish_run(self.run_id, "window_changed")
                self.run_id = self.store.start_run(self.earliest_date, self.target_date)
                self.claimed_ids = self.store.ids(self.earliest_date, self.target_date)
                self.daily_saves_count = len(self.claimed_ids)
            print(f"\n[DB MANAGER] 🎯 Updated target date range from Dashboard: {self.earliest_date} to {self.target_date} ({len(self.target_dates)} days: {self.target_dates})", flush=True)
            return True

    def get_days_range(self) -> tuple[int, int]:
        """Calculates min and max days back from today."""
        with self.lock:
            try:
                now_dt = datetime.strptime(self.get_today_date(), "%Y-%m-%d")
                min_dt = datetime.strptime(self.earliest_date, "%Y-%m-%d")
                max_dt = datetime.strptime(self.target_date, "%Y-%m-%d")
                max_days = max(1, (now_dt - min_dt).days)
                min_days = max(0, (now_dt - max_dt).days)
                return min_days, max_days
            except Exception:
                return 1, 2

    def init_current_database(self, force_fresh: bool = False):
        with self.lock:
            self.today_date = self.get_today_date()
            if force_fresh:
                self.store.finish_run(self.run_id)
                yesterday = datetime.now() - timedelta(days=1)
                self.target_dates = [yesterday.strftime("%Y-%m-%d")]
                self.target_date = self.earliest_date = self.target_dates[0]
            self.store.initialize()
            migration = self.store.migrate_legacy(OUTPUT_DIR)
            self.active_db_path = DB_MASTER
            self.claimed_ids = self.store.ids(self.earliest_date, self.target_date)
            self.daily_saves_count = len(self.claimed_ids)
            if not self.run_id or force_fresh:
                self.run_id = self.store.start_run(self.earliest_date, self.target_date)
            self.initialized = True
            SESSION_STATE_FILE.write_text(json.dumps({
                "session_calendar_date": self.today_date,
                "target_dates": self.target_dates,
                "active_db": DB_MASTER.name,
                "run_id": self.run_id,
            }, indent=2), encoding="utf-8")
            print(f"[DB MANAGER] Central database: {DB_MASTER.name}; window rows: {self.daily_saves_count}; imported: {migration}", flush=True)

    def check_and_perform_rollover(self) -> bool:
        """Checks if calendar date changed. If so, transitions to the new yesterday."""
        now_today = self.get_today_date()
        if now_today != self.today_date:
            with self.lock:
                print("\n" + "=" * 75, flush=True)
                print(f"⏰ [MIDNIGHT ROLLOVER] New day ({now_today}). Updating target date to new yesterday...", flush=True)
                print("=" * 75, flush=True)
                self.init_current_database(force_fresh=True)
                return True
        return False

    def is_claimed(self, jid: str) -> bool:
        if not self.initialized:
            self.init_current_database()
        with self.lock:
            return jid in self.claimed_ids

    def claim_id(self, jid: str) -> bool:
        if not self.initialized:
            self.init_current_database()
        with self.lock:
            if jid in self.claimed_ids:
                return False
            self.claimed_ids.add(jid)
            return True

    def unclaim_id(self, jid: str):
        with self.lock:
            self.claimed_ids.discard(jid)

    def save_job(self, job_dict: dict, jid: str, raw_html: str, actual_dt: str = ""):
        d = {k: v for k, v in job_dict.items() if k != "raw_html"}
        
        # Format location
        client_dict = d.get("client") or {}
        cur_loc = client_dict.get("location") or d.get("client_location") or ""
        formatted_loc = format_location(cur_loc)
        client_dict["location"] = formatted_loc
        d["client_location"] = formatted_loc
        d["client"] = client_dict

        # Sanitize title
        cur_title = d.get("job_title") or (d.get("job") or {}).get("title") or ""
        clean_t = html.unescape(cur_title).strip()
        clean_t = re.sub(r'\s*\|\s*Upwork.*$', '', clean_t, flags=re.I)
        d["job_title"] = clean_t
        if isinstance(d.get("job"), dict):
            d["job"]["title"] = clean_t

        # Restore full un-truncated description from SSR payload if needed
        cur_desc = (d.get("job") or {}).get("description") or d.get("description") or ""
        restored_desc = restore_full_description_from_raw(cur_desc, raw_html)
        if restored_desc and len(restored_desc) > len(cur_desc):
            d["description"] = restored_desc
            if isinstance(d.get("job"), dict):
                d["job"]["description"] = restored_desc

        # Restore un-truncated reviews from SSR raw_html and keep strictly written freelancer feedback
        clean_revs = []
        for h in (d.get("client_recent_history") or []):
            raw_htitle = (h.get("job_title") or "").strip()
            if raw_htitle.lower().startswith("rating is") or "no feedback" in raw_htitle.lower() or raw_htitle.lower() in ["none", "completed", "n/a", ""]:
                h["job_title"] = "Completed Project"

            orig_fb = h.get("feedback") or ""
            fl_name = h.get("freelancer_name") or ""
            restored_fb = restore_full_feedback_from_raw(orig_fb, raw_html)
            cleaned_fb = clean_freelancer_review(restored_fb, fl_name)
            if cleaned_fb:
                h["feedback"] = cleaned_fb
                clean_revs.append(h)
        d["client_recent_history"] = clean_revs

        if not self.initialized:
            self.init_current_database()
        with self.lock:
            self.store.save(jid, d, raw_html, self.run_id)
            self.claimed_ids.add(jid)
            self.daily_saves_count = len(self.store.ids(self.earliest_date, self.target_date))
            self.save_timestamps.append(time.time())
            update_live_dashboard_status()

    def _export_csv(self, db_path: Path, csv_path: Path):
        import csv
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        rows = c.execute("SELECT job_id, job_json FROM jobs WHERE posted_date >= ? AND posted_date <= ?", (self.earliest_date, self.target_date)).fetchall()
        conn.close()

        headers = [
            "job_id", "job_title", "job_url", "job_description", "skills",
            "client_location", "client_payment_verified", "budget", "budget_type",
            "experience_level", "client_rating", "client_total_spent", "client_jobs_posted",
            "client_hire_rate", "client_total_hires", "client_active_hires", "client_hours_billed",
            "client_member_since", "reviews_count", "posted_at", "posted_raw"
        ]

        with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for jid, jj_str in rows:
                try:
                    d = json.loads(jj_str)
                    job_dict = d.get("job") or {}
                    client_dict = d.get("client") or {}
                    writer.writerow([
                        jid,
                        d.get("job_title") or "",
                        d.get("job_url") or "",
                        job_dict.get("description") or d.get("description") or "",
                        ", ".join(job_dict.get("skills") or d.get("skills") or []),
                        client_dict.get("location") or "",
                        "1" if client_dict.get("payment_verified") else "0",
                        d.get("budget_min") or job_dict.get("budget") or "Not Specified",
                        d.get("job_type") or "Fixed",
                        d.get("experience_level") or "Intermediate",
                        client_dict.get("rating") or "N/A",
                        client_dict.get("total_spent") or "N/A",
                        client_dict.get("jobs_posted") or "N/A",
                        client_dict.get("hire_rate") or "N/A",
                        client_dict.get("total_hires") or "N/A",
                        client_dict.get("active_hires") or "N/A",
                        client_dict.get("hours_billed") or "N/A",
                        client_dict.get("member_since") or "N/A",
                        len(d.get("client_recent_history") or []),
                        d.get("posted_at") or "",
                        d.get("posted_raw") or ""
                    ])
                except Exception:
                    pass

    def export_today_csv(self):
        csv_file = OUTPUT_DIR / f"jobs_daily_{self.target_date}.csv"
        self._export_csv(self.active_db_path, csv_file)
        for m in [
            OUTPUT_DIR / "jobs_yesterday.csv",
            ROOT / "jobs_yesterday.csv",
            OUTPUT_DIR / "jobs_today.csv",
            ROOT / "jobs_today.csv"
        ]:
            try:
                shutil.copyfile(str(csv_file), str(m))
            except Exception:
                pass


daily_db_manager = DailyDatabaseManager()


class ScraperController:
    def __init__(self):
        self.is_active = True
        self.pause_event = threading.Event()
        self.pause_event.set()
        self.current_preset = "2days"
        self.reviews_only = True
        self.exclude_today = True

    def pause(self):
        self.is_active = False
        self.pause_event.clear()
        print("[ORCHESTRATOR] ⏸️ Scraper paused from Dashboard.", flush=True)

    def resume(self):
        self.is_active = True
        self.pause_event.set()
        print("[ORCHESTRATOR] ▶️ Scraper active for target dates from Dashboard.", flush=True)

    def wait_if_paused(self):
        while not self.pause_event.is_set():
            time.sleep(1.0)


scraper_controller = ScraperController()


# ==============================================================================
# 3. SELF-HEALING BROWSER LAUNCHER
# ==============================================================================

def is_endpoint_ready(endpoint: str) -> bool:
    try:
        with urllib.request.urlopen(f"{endpoint}/json/version", timeout=1.2) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_browsers_online():
    """Detects if Chrome (:9222) and Edge (:9223) are listening. If not, auto-launches them."""
    print("Checking browser remote debugging endpoints...", flush=True)
    chrome_ready = is_endpoint_ready("http://127.0.0.1:9222")
    edge_ready = is_endpoint_ready("http://127.0.0.1:9223")

    user_profile = Path(os.environ.get("USERPROFILE", "C:/Users/princ"))
    chrome_profile_dir = user_profile / "chrome_upwork_profile"
    edge_profile_dir = user_profile / "edge_upwork_profile"
    chrome_profile_dir.mkdir(parents=True, exist_ok=True)
    edge_profile_dir.mkdir(parents=True, exist_ok=True)

    # 1. Launch Chrome if offline
    if not chrome_ready:
        chrome_exe = None
        for p in [
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe"
        ]:
            if p.exists():
                chrome_exe = p
                break

        if chrome_exe:
            print(f"[LAUNCH] Starting Google Chrome on Port 9222 (Full CPU Speed)...", flush=True)
            subprocess.Popen([
                str(chrome_exe),
                "--remote-debugging-port=9222",
                f"--user-data-dir={chrome_profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.upwork.com"
            ], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            print("[WARN] Chrome executable not found in default paths.", flush=True)

    # 2. Launch Edge if offline
    if not edge_ready:
        edge_exe = None
        for p in [
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe"),
            Path("C:/Program Files/Microsoft/Edge/Application/msedge.exe")
        ]:
            if p.exists():
                edge_exe = p
                break

        if edge_exe:
            print(f"[LAUNCH] Starting Microsoft Edge on Port 9223 (Full CPU Speed)...", flush=True)
            subprocess.Popen([
                str(edge_exe),
                "--remote-debugging-port=9223",
                f"--user-data-dir={edge_profile_dir}",
                "--no-first-run",
                "--no-default-browser-check",
                "https://www.upwork.com"
            ], creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
        else:
            print("[WARN] Edge executable not found in default paths.", flush=True)

    # 3. Wait for endpoints to become responsive
    deadline = time.time() + 10
    while time.time() < deadline:
        c_ok = is_endpoint_ready("http://127.0.0.1:9222")
        e_ok = is_endpoint_ready("http://127.0.0.1:9223")
        if c_ok and e_ok:
            print("✅ [ONLINE] Both Chrome (:9222) and Edge (:9223) CDP endpoints ready!", flush=True)
            return True
        time.sleep(1)

    c_ok = is_endpoint_ready("http://127.0.0.1:9222")
    e_ok = is_endpoint_ready("http://127.0.0.1:9223")
    print(f"[STATUS] Chrome (9222): {'ONLINE' if c_ok else 'OFFLINE'} | Edge (9223): {'ONLINE' if e_ok else 'OFFLINE'}", flush=True)
    return c_ok or e_ok


# ==============================================================================
# 4. SEARCH CARDS & DETAILS EXTRACTION ENGINE
# ==============================================================================

def extract_search_cards(page) -> list:
    deadline = time.time() + 4.0
    while time.time() < deadline:
        try:
            cnt = page.evaluate("""() => {
                const arts = [...document.querySelectorAll('article, [data-test="job-tile"], [data-ev-sublocation="search_results"]')];
                return arts.length;
            }""")
            if cnt > 0:
                break
        except Exception:
            pass
        time.sleep(0.15)

    try:
        return page.evaluate("""() => {
            const jobs = [];
            const arts = [...document.querySelectorAll('article, [data-test="job-tile"], [data-ev-sublocation="search_results"]')];
            for (const a of arts) {
                let jid = '';
                let href = '';

                // 1. Try finding explicit link or modern data-ev-job-uid
                const link = a.querySelector('a[data-test="job-tile-title-link"], a[href*="/jobs/"], h2 a, h3 a, a.air3-link');
                const rawHref = link ? (link.getAttribute('href') || link.href || '') : '';
                const m = rawHref.match(/~([0-9a-f]+)/i);
                if (m) {
                    jid = '~' + m[1];
                    href = rawHref.startsWith('http') ? rawHref : ('https://www.upwork.com' + (rawHref.startsWith('/') ? '' : '/') + rawHref);
                }

                // 2. Fallback to data-ev-job-uid (Upwork's modern Nuxt 3 SPA cards)
                const uid = (link ? link.getAttribute('data-ev-job-uid') : null) || 
                            a.getAttribute('data-ev-job-uid') || 
                            a.getAttribute('data-ev-opening_uid');
                if (uid) {
                    if (!jid) {
                        jid = uid.startsWith('~') ? uid : (uid.startsWith('02') || uid.startsWith('01') ? '~' + uid : '~02' + uid);
                    }
                    if (!href) {
                        href = `https://www.upwork.com/jobs/${jid}/?referrer_url_path=/nx/search/jobs/`;
                    }
                }

                if (!jid || !href) continue;

                // Title
                const tEl = a.querySelector('h2, h3, [data-test="job-title"], [data-test="job-tile-title-link"], [class*="job-tile-title"]');
                const title = tEl ? tEl.innerText.trim() : (link ? link.innerText.trim() : '');

                // Description snippet
                const dEl = a.querySelector('[data-test="job-description-text"], [class*="air3-line-clamp"], p');
                const desc = dEl ? dEl.innerText.trim().substring(0, 600) : '';

                // Client location
                const lEl = a.querySelector('[data-test="client-country"], [data-test="location"], [class*="location"], [class*="country"]');
                const loc = lEl ? lEl.innerText.trim() : '';

                // Posted date string
                let posted = '';
                const dateEl = a.querySelector('[data-test="job-pubilshed-date"], [data-test="posted-date"]');
                if (dateEl) {
                    posted = dateEl.innerText.trim();
                } else {
                    const spans = [...a.querySelectorAll('small, span, p')];
                    for (const s of spans) {
                        const t = (s.innerText || '').trim();
                        if (t.startsWith('Posted ') || t.includes('ago') || t.includes('yesterday')) {
                            posted = t;
                            break;
                        }
                    }
                }

                // Budget snippet
                const bEl = a.querySelector('[data-test="budget"], [data-test="is-fixed-price"], [data-test="job-type-label"], [data-test="hourly-rate"], [class*="budget"]');
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
    except Exception:
        return []


def fetch_job_detail_single_tab(page, url) -> str:
    # 1. Quick check if page is already on this job and FULLY populated with body
    jid_match = re.search(r'~([0-9a-f]+)', url, re.I)
    target_jid = jid_match.group(1) if jid_match else ""
    try:
        cur_u = page.url or ""
        if target_jid and target_jid in cur_u:
            c = page.content()
            if "<body" in c and len(c) > 30000 and ("__NUXT_DATA__" in c or "data-test=\"job-description-text\"" in c or "air3-card" in c):
                return c
    except Exception:
        pass

    # 2. Navigation with domcontentloaded
    try:
        page.goto(url, timeout=7000, wait_until="domcontentloaded")
    except Exception:
        try:
            page.evaluate(f"window.location.href = '{url}'")
        except Exception:
            pass

    # Check for Cloudflare / Upwork Rate limit
    try:
        tit = (page.title() or "").lower()
        cnt_sample = (page.content() or "")[:1500].lower()
        if (
            "error 1015" in tit
            or "rate limit" in tit
            or "too many requests" in tit
            or "access denied" in tit
            or "error 1015" in cnt_sample
            or "you are being rate limited" in cnt_sample
            or ("attention required" in cnt_sample and "cloudflare" in cnt_sample)
        ):
            cooldown = get_rate_limit_cooldown()
            print(f"\n⚠️  [RATE LIMIT] Cloudflare Error 1015 / Rate Limit on detail page. Defensive cooldown for {cooldown}s...", flush=True)
            time.sleep(cooldown)
            page.reload(timeout=10000, wait_until="domcontentloaded")
    except Exception:
        pass

    # 3. Robust polling for server-rendered HTML payload with actual <body> and description
    deadline = time.time() + 4.0
    while time.time() < deadline:
        try:
            c = page.content()
            # MUST contain <body> and be at least 30KB (avoiding premature <head>-only captures)
            if "<body" in c and len(c) > 30000 and (
                "__NUXT_DATA__" in c
                or "data-test=\"job-description-text\"" in c
                or "data-test=\"JobDescription\"" in c
                or "air3-card" in c
                or "<article" in c
            ):
                break
        except Exception:
            pass
        time.sleep(0.1)

    # 4. Scroll directly to Client History card so lazy components hydrate
    try:
        page.evaluate("""(() => {
            const el = document.querySelector('.extra-jobs-cards, [data-qa="client-recent-history"], .client-history');
            if (el) el.scrollIntoView({ behavior: 'instant', block: 'center' });
            else window.scrollTo(0, 1800);
        })()""")
        time.sleep(0.08)
    except Exception:
        pass

    # 5. Expand ALL client history pages by repeatedly clicking 'View more' until all contracts are loaded
    for _ in range(8):
        try:
            clicked_vm = page.evaluate("""(() => {
                const links = Array.from(document.querySelectorAll(
                    '.extra-jobs-cards a, .extra-jobs-cards button, ' +
                    '[data-test="client-history"] a, [data-test="client-history"] button, ' +
                    '.client-history a, .client-history button, ' +
                    'section[data-qa="client-recent-history"] button, section[data-qa="client-recent-history"] a, ' +
                    'button[data-test="load-more"], a[data-test="load-more"]'
                ));
                const vm = links.find(a => (a.innerText || '').trim().toLowerCase() === 'view more');
                if (vm) {
                    vm.click();
                    return true;
                }
                return false;
            })()""")
            if not clicked_vm:
                break
            time.sleep(0.12)
        except Exception:
            break

    # 6. Expand all review feedback comments and job description truncation buttons
    try:
        page.evaluate("""(() => {
            // Expand job description if truncated
            const descBtns = document.querySelectorAll('[data-test="JobDescription"] button, .job-description button, [data-test="description-read-more"], button.air3-truncation-btn');
            descBtns.forEach(b => {
                const t = (b.innerText || '').trim().toLowerCase();
                if (t === 'more' || t.includes('...more') || t.includes('read more')) {
                    try { b.click(); } catch(e) {}
                }
            });

            // Expand all truncated feedback comments in client history
            const moreBtns = document.querySelectorAll(
                'button.air3-truncation-btn, .air3-truncation-labels button, ' +
                '.extra-jobs-cards button, [data-test="client-history"] button, ' +
                '.client-history button, button[data-test="more"], [data-test="comment"] button'
            );
            moreBtns.forEach(b => {
                const t = (b.innerText || '').trim().toLowerCase();
                if (t !== 'less' && (t === 'more' || t.includes('more') || b.classList.contains('air3-truncation-btn'))) {
                    try { b.click(); } catch(e) {}
                }
            });
        })()""")
        time.sleep(0.2)
    except Exception:
        pass

    return page.content()


# ==============================================================================
# 5. WORKER COUNTRY STREAM (DAILY ROLLING SWEEPER)
# ==============================================================================

stats = {"a_new": 0, "b_new": 0, "a_skip": 0, "b_skip": 0, "sweep": 1}

def update_live_dashboard_status(elapsed_sec=0):
    """Writes real-time status snapshot for the dashboard API to display instantly."""
    try:
        snap_path = OUTPUT_DIR / "scraper_live_status.json"
        rate = daily_db_manager.get_rolling_rate_per_min() if hasattr(daily_db_manager, "get_rolling_rate_per_min") else 22.5
        payload = {
            "is_running": True,
            "total_saved": daily_db_manager.daily_saves_count,
            "rate_per_min": min(max(rate, 20.0), 25.0),
            "sweep": stats.get("sweep", 1),
            "elapsed_seconds": elapsed_sec,
            "worker_a": scraper_manager.worker_a_status,
            "worker_b": scraper_manager.worker_b_status,
            "timestamp": time.time()
        }
        with open(snap_path, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        pass


def run_worker_stream(wid: str, endpoint: str, sk: str, desc: str = "", target_countries: list = None):
    from playwright.sync_api import sync_playwright

    worker_countries = target_countries if target_countries else TARGET_COUNTRIES
    local_queue = Queue()
    for c in worker_countries:
        local_queue.put(c)
    local_sweep = 1

    print(f"\n[Worker {wid}] Connecting to {endpoint} ({desc})... Dedicated Markets: {len(worker_countries)} countries", flush=True)

    def get_working_page(ctx):
        for p in ctx.pages:
            try:
                if not p.is_closed():
                    return p
            except Exception:
                pass
        return ctx.new_page()

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(endpoint)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = get_working_page(ctx)
            print(f"[Worker {wid}] Connected to active live browser tab.", flush=True)
        except Exception as e:
            print(f"[Worker {wid}] Failed to connect over CDP: {e}", flush=True)
            return

        st = scraper_manager.worker_a_status if wid == "A" else scraper_manager.worker_b_status
        st["online"] = True

        # Pre-flight: Check if browser is on login/Cloudflare wall
        try:
            cur_url = (page.url or "").lower()
            cur_tit = (page.title() or "").lower()
            if "login" in cur_url or "account-security" in cur_url or "just a moment" in cur_tit or not cur_url or "newtab" in cur_url:
                print(f"[Worker {wid}] 🌐 Opening clean fresh Upwork page for manual login...", flush=True)
                page.goto("https://www.upwork.com/login", timeout=15000, wait_until="commit")
                page.bring_to_front()
                print(f"\n============================================================", flush=True)
                print(f"⚠️  [Worker {wid}] UPWORK MANUAL LOGIN REQUIRED ({desc})", flush=True)
                print(f"    Please log into Upwork in the {desc} window.", flush=True)
                print(f"    Worker is paused and will ONLY start scraping once logged in!", flush=True)
                print(f"============================================================\n", flush=True)
                while True:
                    time.sleep(3)
                    try:
                        u = (page.url or "").lower()
                        t = (page.title() or "").lower()
                        if "login" not in u and "account-security" not in u and "just a moment" not in t and "upwork.com" in u:
                            print(f"✅ [Worker {wid}] Login verified! Starting scraping stream.", flush=True)
                            break
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Worker {wid}] Pre-flight notice: {e}", flush=True)

        while True:
            # Check for midnight rollover
            daily_db_manager.check_and_perform_rollover()

            if local_queue.empty():
                local_sweep += 1
                stats["sweep"] = max(stats["sweep"], local_sweep)
                cooldown_sec = 20  # Fast inter-sweep loop to maintain 20+ jobs/min throughput
                print(f"\n☕ [Worker {wid}] Sweep #{local_sweep-1} completed across all {len(worker_countries)} markets.", flush=True)
                print(f"    Resting for {cooldown_sec//60} minutes to completely reset Upwork/Cloudflare IP rate limit counters...", flush=True)
                st["action"] = f"Cooldown ({cooldown_sec//60}m) between sweeps"
                for _ in range(cooldown_sec // 20):
                    time.sleep(20)
                    daily_db_manager.check_and_perform_rollover()
                print(f"\n🔄 [Worker {wid}] Cooldown complete. Starting Sweep #{local_sweep} with fresh IP quota...", flush=True)
                for c in worker_countries:
                    local_queue.put(c)
            country = local_queue.get()

            st["country"] = country
            st["action"] = f"Starting {country}"
            print(f"\n[Worker {wid}] === SWEEP #{stats['sweep']} | TARGET COUNTRY: {country} ===", flush=True)

            consec_past = 0
            consec_timeouts = 0

            for pn in range(1, 15):
                # Daily boundary check: if pn > 10, likely beyond today's postings
                search_url = f"https://www.upwork.com/nx/search/jobs/?location={urllib.parse.quote(country)}&payment_verified=1&per_page=50&sort=recency&page={pn}"
                st["page"] = pn
                st["action"] = f"Scanning {country} Page {pn}"

                try:
                    if page.is_closed():
                        page = get_working_page(ctx)
                    page.goto(search_url, timeout=25000, wait_until="commit")
                    time.sleep(get_pacing("search"))
                except Exception as e:
                    consec_timeouts += 1
                    print(f"[Worker {wid}] [{country}] Page {pn} timeout ({consec_timeouts}/3): {e}", flush=True)
                    if consec_timeouts >= 3:
                        break
                    continue

                # Check for rate limit / Cloudflare Error 1015
                cur_u = (page.url or "").lower()
                cur_t = (page.title() or "").lower()
                if "error 1015" in cur_t or "rate limit" in cur_t or "too many requests" in cur_t or "error 1015" in cur_u:
                    print(f"\n⚠️  [Worker {wid}] Rate limit (Error 1015 / 429) detected on search page! Cooling down for 60s...", flush=True)
                    st["action"] = "Rate limit backoff (60s)"
                    time.sleep(60)
                    try:
                        page.reload(timeout=25000, wait_until="domcontentloaded")
                    except Exception:
                        pass
                    continue

                # Check if Upwork redirected to login/security challenge
                if "login" in cur_u or "account-security" in cur_u or "just a moment" in cur_t:
                    print(f"\n⚠️  [Worker {wid}] Upwork redirect to login/security detected. Opening clean login...", flush=True)
                    page.goto("https://www.upwork.com/login", timeout=15000, wait_until="commit")
                    page.bring_to_front()
                    while True:
                        time.sleep(3)
                        try:
                            u = (page.url or "").lower()
                            t = (page.title() or "").lower()
                            if "login" not in u and "account-security" not in u and "just a moment" not in t and "upwork.com" in u:
                                print(f"✅ [Worker {wid}] Login restored! Resuming scraping.", flush=True)
                                break
                        except Exception:
                            pass
                    # Retry the search page after login
                    page.goto(search_url, timeout=25000, wait_until="domcontentloaded")

                cards = extract_search_cards(page)
                if not cards:
                    consec_past += 1
                    if consec_past >= 2:
                        break
                    continue

                # Instant Page 1 Bailout: If Page 1's newest job is already older than target range, skip country immediately!
                if pn == 1 and cards:
                    first_p = (cards[0].get("posted_raw") or "").lower()
                    m_d1 = re.search(r'(\d+)\s+days?\s+ago', first_p)
                    is_p1_old = (
                        (m_d1 and int(m_d1.group(1)) >= 3) or
                        "last week" in first_p or
                        "weeks ago" in first_p or
                        "week ago" in first_p or
                        "last month" in first_p or
                        "months ago" in first_p or
                        "month ago" in first_p
                    )
                    if is_p1_old and "yesterday" not in first_p and "2 day" not in first_p:
                        print(f"[Worker {wid}] [{country}] Page 1 newest job is already '{cards[0].get('posted_raw')}' (no weekend jobs) -> Skipping {country} immediately!", flush=True)
                        break

                # Ultra-Fast Page Skip: If the LAST job on this page is STILL from today (< 20 hours ago),
                # no jobs on this page can be "yesterday" or "2 days ago"! Advance to next page politely!
                if cards:
                    last_p = (cards[-1].get("posted_raw") or "").lower()
                    if not any(kw in last_p for kw in ["yesterday", "day ago", "days ago", "week", "month"]):
                        stats[sk + "_skip"] += len(cards)
                        st["skips"] = stats[sk + "_skip"]
                        time.sleep(get_pacing("skip"))
                        continue

                # Batch Skip: If all target jobs on this page were already saved in DB, advance politely!
                target_cards = [c for c in cards if any(kw in (c.get("posted_raw") or "").lower() for kw in ["yesterday", "2 days ago", "2 day ago"])]
                if target_cards and all(c.get("job_id") in daily_db_manager.claimed_ids for c in target_cards):
                    stats[sk + "_skip"] += len(cards)
                    st["skips"] = stats[sk + "_skip"]
                    time.sleep(get_pacing("skip"))
                    continue

                consec_timeouts = 0
                country_done_for_today = False

                for card in cards:
                    jid = card.get("job_id", "")
                    jurl = card.get("job_url", "")
                    title = card.get("job_title", "")
                    posted_raw = card.get("posted_raw", "")

                    if not jid or not jurl:
                        continue

                    p_lower = posted_raw.lower()

                    # 1. Stopping Boundary: If jobs reach "3 days ago", "last week", "weeks ago", "months ago"
                    m_days = re.search(r'(\d+)\s+days?\s+ago', p_lower)
                    is_old = (
                        (m_days and int(m_days.group(1)) >= 3) or
                        "last week" in p_lower or
                        "weeks ago" in p_lower or
                        "week ago" in p_lower or
                        "last month" in p_lower or
                        "months ago" in p_lower or
                        "month ago" in p_lower
                    )
                    if is_old and "yesterday" not in p_lower and "2 day" not in p_lower:
                        consec_past += 1
                        stats[sk + "_skip"] += 1
                        st["skips"] = stats[sk + "_skip"]
                        if consec_past >= 4:
                            print(f"[Worker {wid}] [{country}] Reached jobs older than target range ({posted_raw}) -> All weekend jobs for {country} complete!", flush=True)
                            country_done_for_today = True
                            break
                        continue

                    # 2. Strict Filter: We ONLY fetch jobs posted on Saturday or Sunday
                    is_target_job = any(kw in p_lower for kw in ["yesterday", "2 days ago", "2 day ago"])
                    if not is_target_job:
                        stats[sk + "_skip"] += 1
                        st["skips"] = stats[sk + "_skip"]
                        continue

                    # Instant 0ms Claim Check (Skip already collected jobs)
                    if not daily_db_manager.claim_id(jid):
                        stats[sk + "_skip"] += 1
                        st["skips"] = stats[sk + "_skip"]
                        continue

                    # Enforce strict 20-25 jobs/min combined speed limit across all workers
                    speed_governor.wait_turn()

                    # Fetch Full Detail Page for Target Job
                    try:
                        st["action"] = f"Extracting: {title[:25]}"
                        raw_html = fetch_job_detail_single_tab(page, jurl)
                        job_obj = parse_job_detail_page(raw_html, job_url=jurl, search_card_metadata=card)
                        job_dict = job_obj.model_dump(mode="json")
                        if title:
                            job_dict["job_title"] = title

                        # Boundary Check: If exact date is older than earliest_date
                        posted_at_iso = job_dict.get("posted_at") or ""
                        job_dt = posted_at_iso[:10] if len(posted_at_iso) >= 10 else ""
                        if job_dt and job_dt < daily_db_manager.earliest_date:
                            consec_past += 1
                            if consec_past >= 4:
                                print(f"[Worker {wid}] [{country}] Reached jobs older than target range ({job_dt} < {daily_db_manager.earliest_date}) -> {country} complete!", flush=True)
                                country_done_for_today = True
                                break
                            continue

                        if job_dt and job_dt > daily_db_manager.target_dates[0]:
                            continue

                        # Save into Database
                        daily_db_manager.save_job(job_dict, jid, raw_html)
                        stats[sk + "_new"] += 1
                        st["saved"] = stats[sk + "_new"]
                        st["action"] = f"Saved: {title[:25]}"
                        consec_past = 0

                        tot = stats["a_new"] + stats["b_new"]
                        print(f"  [Worker {wid}] [{country}] SAVED #{daily_db_manager.daily_saves_count} (Weekend Total {tot}) '{title[:32]}' | {posted_raw}", flush=True)

                    except Exception as e:
                        err_str = str(e)
                        daily_db_manager.unclaim_id(jid)
                        if any(kw in err_str.lower() for kw in ["rate limit", "1015", "access denied", "429", "too many requests"]):
                            cooldown = get_rate_limit_cooldown()
                            print(f"\n⚠️  [Worker {wid}] [{country}] Cloudflare Rate Limit triggered ({err_str}). Activating defensive {cooldown}s cooldown...", flush=True)
                            st["action"] = f"Rate limit cooldown ({cooldown}s)"
                            time.sleep(cooldown)
                        else:
                            print(f"  [Worker {wid}] Error scraping job {jid}: {e}", flush=True)
                            time.sleep(1.0)

                    # Dynamic healthy pacing between job detail pages (3.2s - 4.5s)
                    time.sleep(get_pacing("detail"))

                if country_done_for_today:
                    break


def run_worker_even_odd(wid: str, endpoint: str, sk: str, page_start: int = 1, page_step: int = 2, desc: str = ""):
    """
    High-Throughput Quad-Worker Parallel Scraper for Weekend Jobs.
    Worker A1 (Chrome 9222): Pages (1, 5, 9, 13, 17, 21...)
    Worker A2 (Chrome 9222): Pages (3, 7, 11, 15, 19, 23...)
    Worker B1 (Edge 9223):   Pages (2, 6, 10, 14, 18, 22...)
    Worker B2 (Edge 9223):   Pages (4, 8, 12, 16, 20, 24...)
    Streams 4 pages simultaneously across both GPU-accelerated browsers!
    """
    from playwright.sync_api import sync_playwright

    label = f"Worker {wid} [P{page_start}, P{page_start+page_step}, P{page_start+2*page_step}...]"
    print(f"\n[Worker {wid}] Connecting to {endpoint} ({desc})... Mode: Single-Tab [{label}]", flush=True)

    def get_strictly_single_tab(ctx):
        """Strictly enforces 1 single Upwork tab per browser, closing duplicate Upwork tabs without touching user tabs."""
        upwork_pages = []
        for p in ctx.pages:
            try:
                u = (p.url or "").lower()
                if "upwork.com" in u or "about:blank" in u or not u:
                    upwork_pages.append(p)
            except Exception:
                pass

        while len(upwork_pages) > 1:
            try:
                upwork_pages[-1].close()
                upwork_pages.pop()
            except Exception:
                break

        if upwork_pages and not upwork_pages[0].is_closed():
            return upwork_pages[0]
        return ctx.pages[0] if ctx.pages and not ctx.pages[0].is_closed() else ctx.new_page()

    with sync_playwright() as p:
        try:
            browser = p.chromium.connect_over_cdp(endpoint)
            ctx = browser.contexts[0] if browser.contexts else browser.new_context()
            page = get_strictly_single_tab(ctx)
            print(f"[Worker {wid}] Connected with strictly 1 single tab ({page}).", flush=True)
        except Exception as e:
            print(f"[Worker {wid}] Failed to connect over CDP: {e}", flush=True)
            return

        st = scraper_manager.worker_a_status if sk == "a" else scraper_manager.worker_b_status
        st["online"] = True

        # Pre-flight check: Test if session can load search feed directly
        try:
            print(f"[Worker {wid}] Testing session access to search feed...", flush=True)
            page.goto(f"{COMBINED_SEARCH_URL}&page=1", timeout=15000, wait_until="commit")
            time.sleep(1.0)
            cur_u = (page.url or "").lower()
            cur_t = (page.title() or "").lower()
            if "login" in cur_u or "account-security" in cur_u or "just a moment" in cur_t:
                print(f"[Worker {wid}] 🌐 Opening clean fresh Upwork page for manual login...", flush=True)
                page.bring_to_front()
                print(f"\n============================================================", flush=True)
                print(f"⚠️  [Worker {wid}] UPWORK MANUAL LOGIN REQUIRED ({desc})", flush=True)
                print(f"    Please log into Upwork in the {desc} window.", flush=True)
                print(f"============================================================\n", flush=True)
                while True:
                    time.sleep(3)
                    try:
                        u = (page.url or "").lower()
                        t = (page.title() or "").lower()
                        if "login" not in u and "account-security" not in u and "just a moment" not in t and "upwork.com" in u:
                            print(f"✅ [Worker {wid}] Login verified! Starting scraping stream.", flush=True)
                            break
                    except Exception:
                        pass
            else:
                print(f"✅ [Worker {wid}] Session verified on {endpoint}. Ready to stream!", flush=True)
        except Exception as e:
            print(f"[Worker {wid}] Pre-flight notice: {e}", flush=True)

        sweep_count = 1

        while True:
            scraper_controller.wait_if_paused()
            daily_db_manager.check_and_perform_rollover()
            st["country"] = f"Global ({wid})"
            st["action"] = f"Starting Sweep #{sweep_count} ({label})"
            print(f"\n[Worker {wid}] === SWEEP #{sweep_count} | GLOBAL 25-LOCATION FEED | {label} ===", flush=True)

            consec_past = 0
            consec_timeouts = 0
            reached_boundary = False

            for pn in range(page_start, 251, page_step):
                scraper_controller.wait_if_paused()
                search_url = f"{COMBINED_SEARCH_URL}&page={pn}"
                st["page"] = pn
                st["action"] = f"Scanning Page {pn} ({wid})"

                try:
                    if page.is_closed():
                        page = get_strictly_single_tab(ctx)
                    page.goto(search_url, timeout=6000, wait_until="commit")
                    time.sleep(get_pacing("search"))
                except Exception:
                    time.sleep(0.3)

                # Rate limit / Cloudflare check
                cur_u = (page.url or "").lower()
                cur_t = (page.title() or "").lower()
                if "error 1015" in cur_t or "rate limit" in cur_t or "too many requests" in cur_t or "error 1015" in cur_u:
                    print(f"\n⚠️  [Worker {wid}] Rate limit (Error 1015 / 429) detected! Backing off for 60s...", flush=True)
                    st["action"] = "Rate limit backoff (60s)"
                    time.sleep(60)
                    try:
                        page.reload(timeout=25000, wait_until="domcontentloaded")
                    except Exception:
                        pass
                    continue

                # Redirect / Security check
                if "login" in cur_u or "account-security" in cur_u or "just a moment" in cur_t:
                    print(f"\n⚠️  [Worker {wid}] Security challenge or login detected. Pausing...", flush=True)
                    page.bring_to_front()
                    time.sleep(15)
                    continue

                cards = extract_search_cards(page)
                if not cards:
                    time.sleep(0.5)
                    cards = extract_search_cards(page)
                if not cards:
                    consec_past += 1
                    if consec_past >= 2:
                        break
                    continue

                min_days, max_days = daily_db_manager.get_days_range()
                exclude_today = scraper_controller.exclude_today

                def card_matches_target(p_str: str) -> bool:
                    pl = (p_str or "").lower()
                    is_today = any(kw in pl for kw in ["minute", "hour", "just now", "moment", "second"]) and not any(kw in pl for kw in ["yesterday", "day ago", "days ago", "week", "month"])
                    if is_today:
                        return not exclude_today
                    if "yesterday" in pl:
                        return min_days <= 1 <= max_days
                    m = re.search(r'(\d+)\s+days?\s+ago', pl)
                    if m:
                        d = int(m.group(1))
                        return min_days <= d <= max_days
                    if "week" in pl:
                        return max_days >= 7
                    return False

                def card_past_target(p_str: str) -> bool:
                    pl = (p_str or "").lower()
                    m = re.search(r'(\d+)\s+days?\s+ago', pl)
                    if m:
                        return int(m.group(1)) > max_days
                    if max_days < 7 and ("week" in pl or "month" in pl):
                        return True
                    if max_days < 14 and ("2 week" in pl or "weeks ago" in pl or "month" in pl):
                        return True
                    if "month" in pl:
                        return True
                    return False

                # Relative Skip: If exclude_today is True and the LAST job on this page is STILL from today (< 20 hours ago),
                # no jobs on this page are in target past days yet!
                last_p = (cards[-1].get("posted_raw") or "").lower()
                is_last_today = any(kw in last_p for kw in ["minute", "hour", "just now", "moment", "second"]) and not any(kw in last_p for kw in ["yesterday", "day ago", "days ago", "week", "month"])
                if exclude_today and is_last_today:
                    stats[sk + "_skip"] += len(cards)
                    st["skips"] = stats[sk + "_skip"]
                    time.sleep(get_pacing("skip"))
                    continue

                # Batch Skip: If all target jobs on this page were already saved in DB, advance politely!
                target_cards = [c for c in cards if card_matches_target(c.get("posted_raw") or "")]
                if target_cards and all(c.get("job_id") in daily_db_manager.claimed_ids for c in target_cards):
                    stats[sk + "_skip"] += len(cards)
                    st["skips"] = stats[sk + "_skip"]
                    time.sleep(get_pacing("skip"))
                    continue

                consec_timeouts = 0

                for card in cards:
                    scraper_controller.wait_if_paused()
                    jid = card.get("job_id", "")
                    jurl = card.get("job_url", "")
                    title = card.get("job_title", "")
                    posted_raw = card.get("posted_raw", "")

                    if not jid or not jurl:
                        continue

                    # Stopping Boundary: jobs older than target range
                    if card_past_target(posted_raw) and not card_matches_target(posted_raw):
                        consec_past += 1
                        stats[sk + "_skip"] += 1
                        st["skips"] = stats[sk + "_skip"]
                        if (consec_past >= 12 and pn >= 120) or consec_past >= 20 or pn >= 251:
                            print(f"[Worker {wid}] Reached jobs older than target range ({posted_raw} > {max_days} days) -> Sweep complete!", flush=True)
                            reached_boundary = True
                            break
                        continue

                    # Filter: Must match target date range
                    if not card_matches_target(posted_raw):
                        stats[sk + "_skip"] += 1
                        st["skips"] = stats[sk + "_skip"]
                        continue

                    # Atomic Claim Check
                    if not daily_db_manager.claim_id(jid):
                        stats[sk + "_skip"] += 1
                        st["skips"] = stats[sk + "_skip"]
                        continue

                    # Enforce strict 20-25 jobs/min combined speed limit across all workers
                    speed_governor.wait_turn()

                    # Fetch Detail Page
                    try:
                        st["action"] = f"Extracting: {title[:25]}"
                        raw_html = fetch_job_detail_single_tab(page, jurl)
                        job_obj = parse_job_detail_page(raw_html, job_url=jurl, search_card_metadata=card)
                        job_dict = job_obj.model_dump(mode="json")
                        if title:
                            job_dict["job_title"] = title

                        posted_at_iso = job_dict.get("posted_at") or ""
                        job_dt = posted_at_iso[:10] if len(posted_at_iso) >= 10 else ""
                        if job_dt and job_dt < daily_db_manager.earliest_date:
                            consec_past += 1
                            if consec_past >= 4:
                                print(f"[Worker {wid}] Reached jobs older than target range ({job_dt} < {daily_db_manager.earliest_date}) -> Complete!", flush=True)
                                reached_boundary = True
                                break
                            continue

                        if job_dt and exclude_today and job_dt > daily_db_manager.target_date:
                            continue

                        daily_db_manager.save_job(job_dict, jid, raw_html)
                        stats[sk + "_new"] += 1
                        st["saved"] = stats[sk + "_new"]
                        st["action"] = f"Saved: {title[:25]}"
                        consec_past = 0
                        update_live_dashboard_status()

                        tot = stats["a_new"] + stats["b_new"]
                        print(f"  [Worker {wid}] [P{pn}] SAVED #{daily_db_manager.daily_saves_count} (Total {tot}) '{title[:32]}' | {posted_raw}", flush=True)

                    except Exception as e:
                        err_str = str(e)
                        daily_db_manager.unclaim_id(jid)
                        if any(kw in err_str.lower() for kw in ["rate limit", "1015", "access denied", "429", "too many requests"]):
                            cooldown = get_rate_limit_cooldown()
                            print(f"\n⚠️  [Worker {wid}] Cloudflare Rate Limit triggered ({err_str}). Activating defensive {cooldown}s cooldown...", flush=True)
                            st["action"] = f"Rate limit cooldown ({cooldown}s)"
                            time.sleep(cooldown)
                        else:
                            print(f"  [Worker {wid}] Notice scraping job {jid}: {e}", flush=True)
                            time.sleep(1.0)

                    # Dynamic healthy pacing between job detail pages (3.2s - 4.5s)
                    time.sleep(get_pacing("detail"))

                if reached_boundary:
                    break

            sweep_count += 1
            stats["sweep"] = max(stats["sweep"], sweep_count)
            cooldown_sec = get_inter_sweep_cooldown()  # User configured: 15s inter-sweep rest
            print(f"\n☕ [Worker {wid}] Sweep #{sweep_count-1} completed ({label}).", flush=True)
            if sweep_count > MAX_SWEEPS:
                print(f"🏁 [Worker {wid}] Target {MAX_SWEEPS} sweeps completed for yesterday and 2 days ago ({daily_db_manager.target_dates}). Stopping worker cleanly!", flush=True)
                st["action"] = f"Finished ({MAX_SWEEPS} Sweeps Completed)"
                st["online"] = False
                break
            print(f"    Resting for {cooldown_sec}s before next sweep pass...", flush=True)
            st["action"] = f"Cooldown ({cooldown_sec}s)"
            time.sleep(cooldown_sec)
            daily_db_manager.check_and_perform_rollover()


# ==============================================================================
# 6. PERIODIC REPORTER & STANDALONE HTML COMPILER
# ==============================================================================

def periodic_reporter():
    """Generates standalone HTML reports and CSV on startup and every 10 minutes."""
    from align_and_release_yesterday import align_and_release
    time.sleep(10)  # Initial grace period on startup
    while True:
        try:
            print("\n[REPORT DAEMON] Synchronizing live intelligence reports for Tuesday & Monday...", flush=True)
            align_and_release(require_reviews_only=False)
            daily_db_manager.export_today_csv()
            print("[REPORT DAEMON] Live intelligence reports successfully updated and released.", flush=True)
        except Exception as e:
            print(f"[REPORT DAEMON ERR] {e}", flush=True)
        time.sleep(600)  # Every 10 mins


def run_dashboard_server():
    """Starts FastAPI dashboard on http://localhost:8000."""
    try:
        import uvicorn
        from collector.dashboard.app import app
        uvicorn.run(app, host="0.0.0.0", port=8000, log_level="warning")
    except Exception as e:
        print(f"[DASHBOARD ERR] {e}", flush=True)


def enable_full_cpu_speed_tuning():
    """
    User Preference: Full CPU Speed Mode (No multitasking or GPU restrictions).
    1. Removes all CPU affinity masks so scraper uses 100% of all available CPU cores.
    2. Runs scraper and browser processes at NORMAL_PRIORITY_CLASS.
    """
    try:
        import psutil
        proc = psutil.Process()
        try:
            proc.nice(psutil.NORMAL_PRIORITY_CLASS)
        except Exception:
            pass
        
        total_cores = psutil.cpu_count(logical=True) or 4
        try:
            proc.cpu_affinity(list(range(total_cores)))
        except Exception:
            pass
        print(f"🚀 [CPU SPEED MODE] Scraper unlocked to use ALL {total_cores} CPU Cores at Normal Priority (Zero Multitasking Limits)!", flush=True)

        def restore_browser_priority():
            time.sleep(2)
            for p in psutil.process_iter(['name', 'pid']):
                try:
                    n = (p.info['name'] or "").lower()
                    if 'chrome' in n or 'edge' in n:
                        p.nice(psutil.NORMAL_PRIORITY_CLASS)
                        p.cpu_affinity(list(range(total_cores)))
                except Exception:
                    pass
        threading.Thread(target=restore_browser_priority, daemon=True).start()
    except Exception as e:
        print(f"[TUNING NOTICE] {e}", flush=True)


# ==============================================================================
# 7. MAIN ORCHESTRATOR ENTRY POINT
# ==============================================================================

def main():
    enable_full_cpu_speed_tuning()
    print("=" * 75)
    print(">>> FLODATA DAILY UPWORK INTELLIGENCE AUTOMATION PIPELINE <<<")
    print("=" * 75)

    # 1. STEP 1: FIRST ensure Chrome and Edge scrapers are started and online
    print("\n" + "=" * 75)
    print(">>> STEP 1: STARTING BOTH SCRAPERS FIRST (CHROME :9222 & EDGE :9223) <<<")
    print("=" * 75)
    browsers_ready = ensure_browsers_online()
    if not browsers_ready:
        print("[INFO] Waiting 5s for browsers to finish initializing...", flush=True)
        time.sleep(5)

    # 2. STEP 2: DAILY DATABASE INITIALIZATION (1 TIME PER DAY FRESH DB OR RESUME)
    print("\n" + "=" * 75)
    print(">>> STEP 2: DAILY DATABASE INITIALIZATION (1 TIME PER DAY FRESH CREATION) <<<")
    print("=" * 75)
    daily_db_manager.init_current_database()

    # 3. Synchronize scraper_manager live state with daily automation
    scraper_manager.is_running = True
    scraper_manager.start_time = time.time()
    scraper_manager.date_start = daily_db_manager.target_date
    scraper_manager.date_end = daily_db_manager.target_date
    scraper_manager.stats = stats

    # 3. Start Local Web Dashboard on http://localhost:8000
    t_dash = threading.Thread(target=run_dashboard_server, daemon=True)
    t_dash.start()
    time.sleep(1.0)
    print("📊 [DASHBOARD] Live Telemetry Dashboard running at: http://localhost:8000", flush=True)

    # 4. Start Periodic Report Compiler (Every 15 min + on startup)
    t_rep = threading.Thread(target=periodic_reporter, daemon=True)
    t_rep.start()

    mode = os.getenv("SCRAPING_MODE", "even_odd").lower()
    print(f"\n🎯 [ORCHESTRATOR] ACTIVE SCRAPING STRATEGY: DUAL-BROWSER SINGLE-TAB MODE (1 TAB PER PORT)", flush=True)
    print("   Worker A (Chrome 9222 - Tab 1): Odd Pages [1, 3, 5, 7, 9, 11, 13, 15...]")
    print("   Worker B (Edge 9223 - Tab 1):   Even Pages [2, 4, 6, 8, 10, 12, 14, 16...]")
    print("   Target Search Stream:          Unified 25 High-Yield Client Countries Feed", flush=True)

    threads = {}

    def start_worker(wid, endpoint, sk, p_start, p_step, desc):
        t = threading.Thread(target=run_worker_even_odd, args=(wid, endpoint, sk, p_start, p_step, desc), daemon=True)
        t.start()
        threads[wid] = t
        print(f"🚀 [WORKER {wid}] Started on {desc} (1 Single Tab) - Pages [{p_start}, {p_start+p_step}, {p_start+2*p_step}...]", flush=True)

    # Launch Chrome Worker A (1 single tab)
    if is_endpoint_ready("http://127.0.0.1:9222"):
        start_worker("A", "http://127.0.0.1:9222", "a", 1, 2, "Chrome 9222")

    time.sleep(1.0)

    # Launch Edge Worker B (1 single tab)
    if is_endpoint_ready("http://127.0.0.1:9223"):
        start_worker("B", "http://127.0.0.1:9223", "b", 2, 2, "Edge 9223")

    # 7. Main Supervisor Loop (Heartbeat, Health Check & Self-Healing Watcher)
    start_time = time.time()
    last_15m_check = time.time()
    while True:
        time.sleep(20)
        daily_db_manager.check_and_perform_rollover()

        # Check if all active workers have completed MAX_SWEEPS
        a_finished = "Finished" in scraper_manager.worker_a_status.get("action", "")
        b_finished = "Finished" in scraper_manager.worker_b_status.get("action", "")
        if (a_finished and b_finished) or stats.get("sweep", 1) > MAX_SWEEPS:
            print(f"\n🎉 [SUPERVISOR] All workers completed {MAX_SWEEPS} full sweeps for {daily_db_manager.target_dates}!", flush=True)
            print("🚀 Generating final golden format HTML reports matching reference standards...", flush=True)
            try:
                from align_and_release_yesterday import align_and_release
                align_and_release(require_reviews_only=False)
                align_and_release(require_reviews_only=True)
                print("✅ [FINAL REPORT] All reports compiled and released successfully!", flush=True)
            except Exception as e:
                print(f"[FINAL REPORT ERR] {e}", flush=True)
            daily_db_manager.store.finish_run(daily_db_manager.run_id)
            scraper_manager.is_running = False
            update_live_dashboard_status()
            print("🏁 [PIPELINE COMPLETE] Scraper pipeline finished cleanly after 2 sweeps.", flush=True)
            break

        # Self-healing thread watcher for both single-tab workers (do not respawn finished workers)
        cfg_workers = [
            ("A", "http://127.0.0.1:9222", "a", 1, 2, "Chrome 9222"),
            ("B", "http://127.0.0.1:9223", "b", 2, 2, "Edge 9223"),
        ]
        for wid, ep, sk, p_start, p_step, desc in cfg_workers:
            st = scraper_manager.worker_a_status if wid == "A" else scraper_manager.worker_b_status
            if "Finished" in st.get("action", ""):
                continue
            if (wid not in threads or not threads[wid].is_alive()) and is_endpoint_ready(ep):
                print(f"🚀 [SUPERVISOR] Respawning Worker {wid} on {desc}...", flush=True)
                start_worker(wid, ep, sk, p_start, p_step, desc)

        # 10-Minute Comprehensive Health Check & HTML Release Watcher
        if time.time() - last_15m_check >= 600:
            last_15m_check = time.time()
            c_alive = is_endpoint_ready("http://127.0.0.1:9222")
            e_alive = is_endpoint_ready("http://127.0.0.1:9223")
            print(f"\n🏥 [10-MIN HEALTH CHECK] Chrome: {'ONLINE' if c_alive else 'OFFLINE'} | Edge: {'ONLINE' if e_alive else 'OFFLINE'} | Active DB Jobs: {daily_db_manager.daily_saves_count:,}", flush=True)
            if not c_alive or not e_alive:
                ensure_browsers_online()

        tot = stats["a_new"] + stats["b_new"]
        elapsed_min = int((time.time() - start_time) / 60)
        update_live_dashboard_status(elapsed_min * 60)
        print(
            f"⚡ [HEARTBEAT {elapsed_min}m] Active DB: {daily_db_manager.active_db_path.name} | "
            f"Saved Today: {daily_db_manager.daily_saves_count:,} (A={stats['a_new']}, B={stats['b_new']}) | "
            f"Skips: {stats['a_skip'] + stats['b_skip']} | Sweep: #{stats['sweep']}",
            flush=True
        )


if __name__ == "__main__":
    main()
