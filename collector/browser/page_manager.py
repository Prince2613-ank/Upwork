"""
Section 3, 6, 16: Page Manager and Review Expansion Controller.
Handles page interactions, expansion of truncated text, lazy loading, and selector debugging.
"""

import time
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from playwright.sync_api import Page
from collector.config.settings import settings
from collector.logging.logger import logger


class PageManager:
    """Controls DOM interactions, expansion buttons, scrolling, and debug snapshots."""

    def __init__(self, page: Page):
        self.page = page
        try:
            self.page.set_default_timeout(15000)
        except Exception:
            pass

    def polite_delay(self, seconds: Optional[float] = None):
        """Applies jittered delay to pace interactions respectfully."""
        try:
            settings.load()
        except Exception:
            pass
        base = seconds if seconds is not None else settings.delay_between_jobs_seconds
        jitter = random.uniform(0.8, 1.2) * base
        time.sleep(jitter)

    def navigate_to(self, url: str, wait_for_selector: Optional[str] = None):
        """Navigates to URL and waits for content load with retries.
        
        IMPORTANT: Upwork job detail pages render Client History via React/AJAX
        *after* DOM content loads. We must wait for networkidle (or at minimum
        a generous fixed delay) before capturing the page HTML, otherwise the
        history section will be missing entirely.
        """
        logger.info(f"Navigating to {url}")
        for attempt in range(2):
            try:
                # Use 'networkidle' so Upwork's React data fetches complete
                # before we try to extract content. Fall back to domcontentloaded
                # on timeout so we don't block indefinitely.
                try:
                    self.page.goto(url, wait_until="networkidle", timeout=25000)
                except Exception:
                    # networkidle timed out, fall back
                    try:
                        self.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    except Exception:
                        pass
                break
            except Exception as e:
                if attempt == 1:
                    logger.warning(f"Navigation to {url} timed out: {e}")
                    raise
                logger.debug(f"Navigation retry ({attempt+1}/2): {e}")
                time.sleep(1.5)
                
        # Extra wait to allow React components to render history data
        time.sleep(1.5)
        self.dismiss_overlays()
        if wait_for_selector:
            try:
                self.page.wait_for_selector(wait_for_selector, timeout=8000)
            except Exception:
                pass

    def dismiss_overlays(self):
        """Closes any transient tooltip, popover, or onboarding banners that could block views."""
        try:
            self.page.evaluate("""() => {
                const closeBtns = document.querySelectorAll(
                    'button.air3-popper-close, [data-test="popper-close-btn"], button[aria-label="Close"], .air3-popover button, [aria-label*="close" i]'
                );
                closeBtns.forEach(b => {
                    try { b.click(); } catch(e) {}
                });
            }""")
        except Exception:
            pass

    def get_content(self) -> str:
        """Retrieves page HTML safely, waiting only if page is mid-navigation."""
        for attempt in range(8):
            try:
                html = self.page.content()
                if html:
                    return html
            except Exception:
                pass
            time.sleep(0.25)
        try:
            return self.page.evaluate("() => document.documentElement.outerHTML") or ""
        except Exception:
            return ""

    def scroll_to_bottom(self):
        """Scrolls down smoothly to trigger lazy-loaded sections.
        
        Upwork uses virtual scrolling / intersection observers for the Client
        History section. We scroll in multiple steps with pauses so every
        lazy-loaded batch gets a chance to render.
        """
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.3);")
            time.sleep(0.4)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.6);")
            time.sleep(0.4)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.85);")
            time.sleep(0.4)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)  # Wait for lazy sections to render
        except Exception as e:
            logger.debug(f"Scroll evaluation notice: {e}")

    def expand_description(self):
        """
        Expands full job description if 'More' / 'Show more' button exists.
        Section 3 & Section 7.
        """
        try:
            expander_selectors = [
                "[data-test='job-description-text'] button",
                ".job-description button:has-text('More')",
                "[data-test='Description'] button",
                "button[aria-expanded='false']:has-text('More')",
            ]
            for sel in expander_selectors:
                btn = self.page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    txt = btn.first.inner_text().strip().lower()
                    if "more" in txt:
                        btn.first.click()
                        time.sleep(0.2)
                        logger.info("Clicked job description 'More' expander.")
                        break
        except Exception as e:
            logger.debug(f"Description expander not clicked: {e}")

    def wait_for_history_section(self, timeout_s: float = 12.0) -> bool:
        """
        Waits until Upwork's React-rendered Client History section appears
        in the DOM. Returns True if the section was found, False on timeout.
        
        Upwork renders the history section asynchronously via an AJAX call
        after the page DOM loads. This method polls for various known selectors
        and text patterns that indicate the history section is present.
        """
        history_check_js = """
        () => {
            // Check for text content indicating history section is rendered
            const allText = document.body ? document.body.innerText : '';
            if (allText.toLowerCase().includes("client's recent history") ||
                allText.toLowerCase().includes('recent history')) {
                return true;
            }
            // Check for known container selectors
            const selectors = [
                '[data-test="client-history"]',
                '[data-test="contract-history"]',
                '[data-cy="client-history"]',
                '.client-history',
                '#client-history',
            ];
            for (const sel of selectors) {
                if (document.querySelector(sel)) return true;
            }
            return false;
        }
        """
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            try:
                found = self.page.evaluate(history_check_js)
                if found:
                    logger.info("Client History section detected in DOM.")
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        logger.debug("Client History section not detected within timeout (client may have 0 contracts).")
        return False

    def expand_history_pagination(self, max_clicks: int = 30) -> int:
        """
        Client's Recent History initially renders only the first ~5 contract
        cards. Two independent controls can hide additional ones:
        - A collapsed "Jobs in progress" toggle, which reveals active
          (not-yet-completed) contracts that are otherwise omitted entirely.
        - A "View more (N)" link that progressively loads older batches of
          completed contracts.
        Without expanding both, only those first ~5 cards ever reach the DOM
        regardless of the true total (e.g. "(7)" or "(50)" in the heading).
        
        IMPORTANT: Wait for the history section to appear first, since it
        loads asynchronously via AJAX after page DOM is ready.
        """
        # Wait for history section to actually render (AJAX-loaded)
        self.wait_for_history_section(timeout_s=12.0)
        
        # Extra scroll to ensure the history section is visible to lazy loaders
        try:
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight * 0.7);")
            time.sleep(0.6)
            self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)
        except Exception:
            pass

        # 1. Expand "Jobs in progress" toggle if present
        try:
            expanded_progress = self.page.evaluate(
                """() => {
                    // Try multiple selectors for the jobs-in-progress toggle
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
                }"""
            )
            if expanded_progress:
                time.sleep(1.0)  # Wait for in-progress contracts to render
                logger.info("Expanded 'Jobs in progress' section.")
        except Exception as e:
            logger.debug(f"Jobs-in-progress toggle not clicked: {e}")

        # 2. Click "View more" links to load all history batches
        click_js = """
        (() => {
            // Match 'View more', 'view more (N)', 'Show more', 'Load more'
            const allLinks = Array.from(document.querySelectorAll('a, button'));
            const target = allLinks.find(el => {
                const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
                return txt.startsWith('view more') || txt.startsWith('show more') ||
                       txt.startsWith('load more') || txt === 'view all';
            });
            if (target) {
                target.click();
                return true;
            }
            return false;
        })()
        """
        clicks = 0
        for _ in range(max_clicks):
            try:
                clicked = self.page.evaluate(click_js)
            except Exception:
                break
            if not clicked:
                break
            clicks += 1
            time.sleep(0.5)  # Wait for each batch to render before next click
        if clicks:
            logger.info(f"Expanded Client History pagination: clicked 'View more' {clicks}x.")
        return clicks

    def expand_all_reviews(self) -> int:
        """
        Section 6: Review / Feedback Expansion.
        Detects and clicks all expandable controls ('More', 'Show more', 'aria-expanded')
        in Client's Recent History.
        """
        expand_js = """
        (() => {
            let count = 0;
            // Target client history and feedback buttons
            const selectors = [
                '[data-test="client-history"] button',
                '.client-history button',
                '[data-test="feedback-comment"] button',
                '.feedback-comment button',
                'button[aria-label*="more"]',
                'button[aria-expanded="false"]'
            ];
            const buttons = document.querySelectorAll(selectors.join(', '));
            buttons.forEach(b => {
                const txt = (b.innerText || b.textContent || '').trim().toLowerCase();
                if (txt === 'more' || txt === 'show more' || txt === 'read more' || txt.includes('...more')) {
                    try {
                        b.click();
                        count++;
                    } catch(e) {}
                }
            });
            return count;
        })()
        """
        try:
            clicked = self.page.evaluate(expand_js)
            if clicked > 0:
                logger.info(f"Expanded {clicked} truncated reviews in Client History.")
                time.sleep(0.15)
            return clicked
        except Exception as e:
            logger.debug(f"Review expansion script notice: {e}")
            return 0

    def capture_debug_snapshot(
        self,
        job_url: str,
        selector_attempted: str,
        html_snippet: str = "",
    ):
        """
        Section 16: DOM Inspection / Selector Debugging Mode.
        Saves URL, HTML snippet, selector attempted, screenshot, and timestamp.
        """
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        clean_name = f"debug_{timestamp}"
        snap_dir = settings.debug_snapshots_path
        snap_dir.mkdir(parents=True, exist_ok=True)

        # 1. Save screenshot
        screenshot_path = snap_dir / f"{clean_name}.png"
        try:
            self.page.screenshot(path=str(screenshot_path), full_page=True)
        except Exception:
            pass

        # 2. Save metadata & HTML snippet
        meta_path = snap_dir / f"{clean_name}.json"
        snippet = html_snippet or (self.page.content()[:5000] if self.page else "")
        meta = {
            "timestamp": timestamp,
            "url": job_url or self.page.url,
            "selector_attempted": selector_attempted,
            "screenshot_file": str(screenshot_path.name),
            "html_snippet": snippet[:4000],
        }
        try:
            import json
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            logger.warning(f"Saved selector debug snapshot to {meta_path}")
        except Exception as e:
            logger.debug(f"Error writing debug snapshot: {e}")
