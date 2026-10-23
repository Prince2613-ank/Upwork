"""
Flodata - Single Chrome Scraper (Port 9222 only)
================================================
- Uses the ONE logged-in Chrome on port 9222
- Waits for React to render job cards (not just HTML)
- Extracts job data directly via JavaScript from live DOM
- Properly waits for client history section to load
- Saves all details to database_14days.db
- Run: python fetch_single_chrome.py
"""

import os
import sys
import time
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.abspath("."))

PROJECT_DIR = Path(__file__).parent.resolve()
OUTPUT_DIR = PROJECT_DIR / "output"
DB_14DAYS = OUTPUT_DIR / "database_14days.db"
OUTPUT_DIR.mkdir(exist_ok=True)

PORT = 9222

BASE_SEARCH_URL = (
    "https://www.upwork.com/nx/search/jobs?"
    "location=Europe,Australia%2520and%2520New%2520Zealand,American%2520Samoa,Bahamas,Bahrain,Belgium,Canada,Cayman%2520Islands,"
    "Hong%2520Kong,India,Israel,Japan,Kuwait,Malaysia,Morocco,New%2520Zealand,Qatar,Saudi%2520Arabia,Singapore,South%2520Korea,"
    "United%2520Arab%2520Emirates,United%2520Kingdom,United%2520States,United%2520States%2520Minor%2520Outlying%2520Islands,"
    "United%2520States%2520Virgin%2520Islands&payment_verified=1&per_page=50&sort=recency"
)

MAX_PAGES = 100  # Scrape up to 100 pages

from collector.extraction.job_parser import parse_job_detail_page


# ─── Database ────────────────────────────────────────────────────────────────

def init_db() -> set:
    conn = sqlite3.connect(DB_14DAYS, timeout=30)
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("CREATE TABLE IF NOT EXISTS jobs (job_id TEXT PRIMARY KEY, job_json TEXT)")
    conn.commit()
    existing = set(r[0] for r in c.execute("SELECT job_id FROM jobs").fetchall())
    conn.close()
    print(f"[DB] Existing jobs: {len(existing):,}", flush=True)
    return existing


def save_job(job_dict: dict, job_id: str):
    raw_json = json.dumps(job_dict, default=str)
    conn = sqlite3.connect(DB_14DAYS, timeout=30)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO jobs (job_id, job_json) VALUES (?, ?)", (job_id, raw_json))
    conn.commit()
    conn.close()


# ─── Page helpers ─────────────────────────────────────────────────────────────

def wait_cloudflare(page, timeout_sec=20):
    for _ in range(timeout_sec):
        try:
            t = page.title().lower()
            if "just a moment" not in t and "attention required" not in t:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def extract_job_cards_js(page) -> list:
    """
    Extract job cards directly from the React DOM using JavaScript.
    Waits up to 20s for cards to render.
    """
    # Wait for job cards to appear
    wait_js = """
    () => {
        // Try multiple selectors for job cards
        const selectors = [
            '[data-test="job-tile"]',
            '[data-test="JobTile"]', 
            'article[data-job-uid]',
            'article[class*="job"]',
            '[class*="job-tile"]',
            '[class*="JobTile"]',
            'section[data-test="job-search-results"] article',
            '[data-ev-label="search_results"] article',
            '.job-tile',
        ];
        for (const sel of selectors) {
            const els = document.querySelectorAll(sel);
            if (els.length > 0) return {found: true, count: els.length, selector: sel};
        }
        // Fallback: check for any article with job URL
        const articles = Array.from(document.querySelectorAll('article, li[data-test]'));
        const jobArticles = articles.filter(a => {
            const links = a.querySelectorAll('a[href*="/jobs/"]');
            return links.length > 0;
        });
        if (jobArticles.length > 0) return {found: true, count: jobArticles.length, selector: 'article_with_job_link'};
        return {found: false, count: 0, selector: null};
    }
    """
    
    deadline = time.time() + 20
    selector_used = None
    while time.time() < deadline:
        try:
            result = page.evaluate(wait_js)
            if result.get('found'):
                selector_used = result.get('selector')
                print(f"  [Cards] Found {result['count']} cards using: {selector_used}", flush=True)
                break
        except Exception:
            pass
        time.sleep(0.5)
    
    if not selector_used:
        print("  [Cards] No job cards found after 20s wait", flush=True)
        return []
    
    # Extract job data from found cards
    extract_js = f"""
    () => {{
        const jobs = [];
        
        // Find all articles/tiles that contain job links
        const articles = Array.from(document.querySelectorAll('article, li[data-test], [data-test="job-tile"]'));
        
        for (const article of articles) {{
            const jobLinks = Array.from(article.querySelectorAll('a[href*="/jobs/"]'));
            if (jobLinks.length === 0) continue;
            
            const link = jobLinks[0];
            const href = link.href || '';
            
            // Extract job ID from URL
            const idMatch = href.match(/~([0-9a-f]+)/i) || href.match(/_([0-9]+)\/?$/);
            const jobId = idMatch ? ('~' + idMatch[1]) : '';
            
            if (!jobId || !href.includes('/jobs/')) continue;
            
            // Get title
            const titleEl = article.querySelector('h2, h3, [data-test="job-title"], [class*="title"]');
            const title = titleEl ? titleEl.innerText.trim() : link.innerText.trim();
            
            // Get description snippet
            const descEl = article.querySelector('[data-test="job-description-text"], [class*="description"], p');
            const desc = descEl ? descEl.innerText.trim() : '';
            
            // Get posted time  
            const timeEl = article.querySelector('time, [data-test="posted-on"], [class*="posted"]');
            const posted = timeEl ? (timeEl.getAttribute('datetime') || timeEl.innerText.trim()) : '';
            
            // Get budget/rate
            const budgetEl = article.querySelector('[data-test="budget"], [class*="budget"], [class*="rate"]');
            const budget = budgetEl ? budgetEl.innerText.trim() : '';
            
            // Get client location
            const locEl = article.querySelector('[data-test="client-country"], [class*="location"], [class*="country"]');
            const location = locEl ? locEl.innerText.trim() : '';
            
            // Get payment verified
            const payEl = article.querySelector('[data-test="payment-verified"], [class*="payment"]');
            const paymentVerified = payEl ? payEl.innerText.trim() : '';
            
            if (title && href) {{
                jobs.push({{
                    job_id: jobId,
                    job_url: href,
                    job_title: title,
                    description_snippet: desc.substring(0, 500),
                    posted_raw: posted,
                    budget: budget,
                    client_location: location,
                    payment_verified: paymentVerified,
                }});
            }}
        }}
        return jobs;
    }}
    """
    
    try:
        cards = page.evaluate(extract_js)
        print(f"  [Cards] Extracted {len(cards)} job cards from DOM", flush=True)
        return cards or []
    except Exception as e:
        print(f"  [Cards] JS extraction error: {e}", flush=True)
        return []


def wait_for_history(page, timeout_s=15.0) -> bool:
    """Poll until client history section appears (React AJAX rendered)."""
    check_js = """
    () => {
        const text = document.body ? document.body.innerText : '';
        if (text.toLowerCase().includes("client's recent history") ||
            text.toLowerCase().includes("recent history")) return true;
        const selectors = [
            '[data-test="client-history"]',
            '[data-test="contract-history"]',
            '.client-history',
        ];
        return selectors.some(s => document.querySelector(s));
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


def fetch_job_detail(page, jurl: str) -> str:
    """Navigate to job page, wait for history to load, return full HTML."""
    try:
        page.goto(jurl, timeout=35000, wait_until="domcontentloaded")
    except Exception:
        try:
            page.goto(jurl, timeout=35000, wait_until="commit")
        except Exception:
            pass

    wait_cloudflare(page, timeout_sec=12)
    time.sleep(2.0)

    # Scroll gradually to trigger lazy loading
    for pct in [0.25, 0.5, 0.75, 1.0]:
        try:
            page.evaluate(f"window.scrollTo(0, document.body.scrollHeight * {pct})")
        except Exception:
            pass
        time.sleep(0.35)

    # Wait for history section
    found = wait_for_history(page, timeout_s=15.0)
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
            for (const btn of candidates) { if (btn) { btn.click(); return true; } }
            return false;
        }
        """)
        if clicked:
            time.sleep(1.0)
    except Exception:
        pass

    # Click "View more" links to load all history batches
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


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    from playwright.sync_api import sync_playwright

    start = time.time()
    print("=" * 65, flush=True)
    print("  FLODATA - SINGLE CHROME SCRAPER (Port 9222)", flush=True)
    print(f"  DB: {DB_14DAYS}", flush=True)
    print("=" * 65, flush=True)

    existing_ids = init_db()
    fetched = 0
    skipped = 0
    errors = 0

    with sync_playwright() as pw:
        browser = pw.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}", timeout=15000)
        ctx = browser.contexts[0]

        # Fresh pages
        search_page = ctx.new_page()
        detail_page = ctx.new_page()

        for page_num in range(1, MAX_PAGES + 1):
            search_url = f"{BASE_SEARCH_URL}&page={page_num}"
            print(f"\n[Page {page_num}] Loading search...", flush=True)

            # Load search page and wait for React to render cards
            for attempt in range(3):
                try:
                    search_page.goto(search_url, timeout=45000, wait_until="domcontentloaded")
                    wait_cloudflare(search_page, timeout_sec=20)
                    time.sleep(3)
                    break
                except Exception as e:
                    print(f"  Search page attempt {attempt+1} error: {e}", flush=True)
                    try:
                        search_page.close()
                    except Exception:
                        pass
                    search_page = ctx.new_page()
                    time.sleep(2)

            cards = extract_job_cards_js(search_page)
            print(f"[Page {page_num}] {len(cards)} cards", flush=True)

            if not cards:
                if page_num <= 3:
                    print(f"[Page {page_num}] No cards — may need login. Waiting 10s...", flush=True)
                    time.sleep(10)
                    cards = extract_job_cards_js(search_page)
                if not cards:
                    print(f"[Page {page_num}] Still no cards. Stopping.", flush=True)
                    break

            page_new = 0
            page_old = 0

            for card in cards:
                jid = card.get("job_id", "")
                jurl = card.get("job_url", "")
                if not jid or not jurl or "/jobs/" not in jurl:
                    continue

                if jid in existing_ids:
                    skipped += 1
                    page_old += 1
                    continue

                title = card.get("job_title", "")[:45]
                print(f"  Fetching: '{title}'", flush=True)

                for attempt in range(2):
                    try:
                        detail_html = fetch_job_detail(detail_page, jurl)
                        job_obj = parse_job_detail_page(detail_html, job_url=jurl, search_card_metadata=card)
                        job_dict = job_obj.model_dump(mode="json")

                        # Sync title from search card
                        if card.get("job_title"):
                            job_dict["job_title"] = card["job_title"]

                        hist = len(job_dict.get("client_recent_history") or [])
                        save_job(job_dict, jid)
                        existing_ids.add(jid)
                        fetched += 1
                        page_new += 1
                        print(f"  ✓ #{fetched} '{title}' | History: {hist}", flush=True)
                        break
                    except Exception as e:
                        if attempt == 0:
                            print(f"  Retry {jid}: {e}", flush=True)
                            try:
                                detail_page.close()
                            except Exception:
                                pass
                            detail_page = ctx.new_page()
                        else:
                            errors += 1
                            print(f"  ✗ Error {jid}: {e}", flush=True)

            print(f"[Page {page_num}] Done: +{page_new} new, {page_old} already in DB", flush=True)

            # If mostly old jobs, we've caught up
            if page_old > 30 and page_new == 0:
                print(f"All jobs on page {page_num} already in DB — fully caught up!", flush=True)
                break

        try:
            search_page.close()
            detail_page.close()
        except Exception:
            pass
        browser.close()

    elapsed = int(time.time() - start)
    total = sqlite3.connect(DB_14DAYS).execute("SELECT COUNT(*) FROM jobs").fetchone()[0]
    print("\n" + "=" * 65, flush=True)
    print(f"  DONE in {elapsed//60}m {elapsed%60}s", flush=True)
    print(f"  New fetched: {fetched} | Skipped: {skipped} | Errors: {errors}", flush=True)
    print(f"  Total in DB: {total:,}", flush=True)
    print("=" * 65, flush=True)


if __name__ == "__main__":
    main()
