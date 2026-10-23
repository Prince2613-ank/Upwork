"""
Playwright-based Browser Data Source.
Attaches to an authorized Chrome session over CDP or launches a supervised persistent session.
Implements complete review un-truncation, full description extraction, polite pacing,
and safe restriction handling.
"""

import asyncio
import logging
import random
import time
from typing import List, Dict, Any, Tuple, Optional
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Error as PlaywrightError
from config import (
    build_search_url,
    CHROME_CDP_URL,
    BROWSER_HEADLESS,
    USER_DATA_DIR,
    MIN_REQUEST_DELAY_SEC,
    MAX_REQUEST_DELAY_SEC,
    MAX_RETRIES,
    BACKOFF_FACTOR,
)
from .base import BaseDataSource

logger = logging.getLogger(__name__)


class PlaywrightBrowserDataSource(BaseDataSource):
    """
    Supervised browser automation source using Playwright.
    Connects to the user's active authenticated Chrome session over CDP
    (http://localhost:9222) or uses a persistent browser profile.
    """

    def __init__(self, cdp_url: str = CHROME_CDP_URL, use_cdp: bool = True):
        self.cdp_url = cdp_url
        self.use_cdp = use_cdp
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self._init_browser()

    def _init_browser(self):
        """Initializes Playwright connection to Chrome."""
        self.playwright = sync_playwright().start()
        if self.use_cdp:
            try:
                logger.info(f"Connecting to authorized Chrome instance via CDP at {self.cdp_url}...")
                self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url)
                if self.browser.contexts:
                    self.context = self.browser.contexts[0]
                else:
                    self.context = self.browser.new_context()
                if self.context.pages:
                    self.page = self.context.pages[0]
                else:
                    self.page = self.context.new_page()
                logger.info("Successfully attached to active Chrome CDP session.")
                return
            except Exception as e:
                logger.warning(
                    f"Could not connect to Chrome CDP at {self.cdp_url} ({e}). "
                    f"Falling back to supervised persistent browser context."
                )

        # Fallback to local persistent browser session
        USER_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self.context = self.playwright.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=BROWSER_HEADLESS,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
        )
        self.page = self.context.pages[0] if self.context.pages else self.context.new_page()

    def _polite_delay(self):
        """Paces requests to respect platform load and avoid burst patterns."""
        delay = random.uniform(MIN_REQUEST_DELAY_SEC, MAX_REQUEST_DELAY_SEC)
        time.sleep(delay)

    def fetch_search_page(self, page: int = 1) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Navigates to the search results page and extracts job summary links.
        """
        url = build_search_url(page=page)
        logger.info(f"Navigating to search page {page}: {url}")

        retries = 0
        while retries <= MAX_RETRIES:
            try:
                self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
                self._polite_delay()

                # Check for login redirection or security prompt
                current_url = self.page.url
                if "/account-security/login" in current_url or "login" in current_url.lower():
                    logger.error(
                        "Upwork redirected to login page. Authorized user session required. "
                        "Please ensure Chrome is logged in with your active account."
                    )
                    raise PermissionError("Authentication required on Upwork.")

                # Wait for job tiles to load
                try:
                    self.page.wait_for_selector(
                        "[data-test='job-tile-list'], article[data-test='JobTile'], .up-card-section",
                        timeout=15000,
                    )
                except Exception:
                    logger.warning("Job tile list selector timed out, attempting extraction on current DOM...")

                # Parse search page DOM for job summaries
                content = self.page.content()
                soup = BeautifulSoup(content, "html.parser")

                job_elements = soup.select(
                    "article[data-test='JobTile'], [data-test='JobTile'], .job-tile, article"
                )

                job_summaries = []
                for el in job_elements:
                    link = el.select_one("a[href*='/jobs/']")
                    if not link:
                        continue
                    href = link["href"]
                    if not href.startswith("http"):
                        href = f"https://www.upwork.com{href}"

                    title = link.get_text().strip()
                    time_el = el.select_one("[data-test='posted-on'], time, .posted-date")
                    posted_raw = time_el.get_text().strip() if time_el else ""

                    # Extract job ID
                    from parsers.job_parser import extract_job_id_from_url
                    jid = extract_job_id_from_url(href)
                    if jid:
                        job_summaries.append(
                            {
                                "job_id": jid,
                                "job_url": href,
                                "title": title,
                                "posted_raw": posted_raw,
                            }
                        )

                # Check if there is a next page button
                has_more = bool(soup.select_one("button[data-test='next-page']:not([disabled]), .pagination-next:not(.disabled)"))
                logger.info(f"Page {page}: Extracted {len(job_summaries)} job links. Has more: {has_more}")
                return job_summaries, has_more

            except PermissionError:
                raise
            except Exception as e:
                retries += 1
                wait_sec = BACKOFF_FACTOR ** retries
                logger.warning(f"Error fetching search page {page} ({e}). Retrying in {wait_sec:.1f}s (attempt {retries}/{MAX_RETRIES})...")
                time.sleep(wait_sec)

        raise RuntimeError(f"Failed to fetch search page {page} after {MAX_RETRIES} retries.")

    def fetch_job_details(self, job_id: str, job_url: str) -> str:
        """
        Navigates to individual job details, clicks all expansion controls
        for full description and complete review text, and returns full HTML.
        """
        logger.info(f"Fetching full job details for {job_id} ({job_url})...")
        self._polite_delay()

        retries = 0
        while retries <= MAX_RETRIES:
            try:
                self.page.goto(job_url, wait_until="domcontentloaded", timeout=45000)
                self._polite_delay()

                # Expand full job description if 'more' button exists
                try:
                    desc_more_btn = self.page.locator(
                        "[data-test='job-description-text'] button, .job-description button:has-text('More')"
                    )
                    if desc_more_btn.count() > 0 and desc_more_btn.first.is_visible():
                        desc_more_btn.first.click()
                        time.sleep(0.5)
                except Exception as e:
                    logger.debug(f"Description expander not clicked: {e}")

                # Scroll to About Client and History
                try:
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight / 2);")
                    time.sleep(1.0)
                    self.page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.0)
                except Exception:
                    pass

                # CRITICAL: Click all "More" buttons in the Client History feedback list!
                # Manager requirement: "The COMPLETE review/feedback must be captured."
                try:
                    expand_script = """
                    (() => {
                        let clickedCount = 0;
                        // Select all More buttons within client history or feedback sections
                        const buttons = document.querySelectorAll(
                            '[data-test="client-history"] button, .client-history button, .feedback-content button, [data-test="feedback-comment"] button'
                        );
                        buttons.forEach(btn => {
                            const txt = (btn.innerText || btn.textContent || '').trim().toLowerCase();
                            if (txt === 'more' || txt === 'read more') {
                                btn.click();
                                clickedCount++;
                            }
                        });
                        return clickedCount;
                    })()
                    """
                    expanded = self.page.evaluate(expand_script)
                    if expanded > 0:
                        logger.info(f"Expanded {expanded} truncated reviews in client history.")
                        time.sleep(1.0)
                except Exception as e:
                    logger.debug(f"Error executing review expansion script: {e}")

                return self.page.content()

            except Exception as e:
                retries += 1
                wait_sec = BACKOFF_FACTOR ** retries
                logger.warning(f"Error fetching job details for {job_id} ({e}). Retrying in {wait_sec:.1f}s...")
                time.sleep(wait_sec)

        raise RuntimeError(f"Failed to fetch job details for {job_id} after {MAX_RETRIES} retries.")

    def close(self):
        """Cleans up browser resources."""
        try:
            if self.page:
                self.page.close()
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error closing browser: {e}")
