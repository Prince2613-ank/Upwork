"""
Section 10 & 15: Browser Manager.
Attaches to the user's active, authenticated Chrome session over CDP (port 9222)
or launches a persistent browser session.
Monitors for security restrictions (CAPTCHA, verification, login prompts) and stops safely.
"""

import time
from typing import Optional, Tuple
from playwright.sync_api import sync_playwright, Browser, BrowserContext, Page, Error as PlaywrightError
from collector.config.settings import settings
from collector.logging.logger import logger


class SecurityRestrictionError(Exception):
    """Raised when Upwork displays CAPTCHA, login prompt, or security verification."""
    pass


class BrowserManager:
    """Manages Playwright lifecycle and session preservation."""

    def __init__(self, cdp_url: Optional[str] = None, new_tab: bool = False):
        self.cdp_url = cdp_url or settings.cdp_url
        self.new_tab = new_tab
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.connected_via_cdp = False

    def start(self) -> Page:
        """Initializes browser connection to active Chrome session."""
        self.playwright = sync_playwright().start()

        # Attempt 1: Connect to active Chrome session via CDP
        try:
            logger.info(f"Attempting to attach to authorized Chrome session via CDP at {self.cdp_url}...")
            self.browser = self.playwright.chromium.connect_over_cdp(self.cdp_url, timeout=15000)
            if self.browser.contexts:
                self.context = self.browser.contexts[0]
            else:
                self.context = self.browser.new_context()

            if self.new_tab:
                self.page = self.context.new_page()
                logger.info("Created dedicated worker tab in authorized Chrome session.")
                try:
                    self.page.goto("https://www.upwork.com", timeout=15000)
                    time.sleep(1.5)
                except Exception as e:
                    logger.debug(f"Tab warmup note: {e}")
            else:
                # Find existing Upwork tab if open
                upwork_page = None
                for p in self.context.pages:
                    if "upwork.com" in p.url.lower():
                        upwork_page = p
                        break

                if upwork_page:
                    self.page = upwork_page
                    logger.info(f"Attached to existing Upwork tab: {self.page.url}")
                elif self.context.pages:
                    self.page = self.context.pages[0]
                    logger.info(f"Using open tab: {self.page.url}")
                else:
                    self.page = self.context.new_page()

            self.connected_via_cdp = True
            logger.info("Successfully connected to Chrome via CDP.")
            return self.page

        except Exception as e:
            logger.warning(
                f"Chrome CDP connection to {self.cdp_url} unavailable ({e}). "
                f"Attempting supervised persistent browser session..."
            )

        # Attempt 2: Persistent context with user profile directory
        user_data_dir = settings.output_path / "browser_profile"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.context = self.playwright.chromium.launch_persistent_context(
                user_data_dir=str(user_data_dir),
                headless=settings.headless,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-first-run",
                    "--no-default-browser-check",
                ],
            )
            self.page = self.context.pages[0] if self.context.pages else self.context.new_page()
            self.connected_via_cdp = False
            logger.info("Launched persistent browser session.")
            return self.page
        except Exception as e:
            logger.error(f"Failed to launch persistent Chrome context: {e}")
            raise

    def check_security_restrictions(self, page: Page):
        """
        Detects CAPTCHA, login requests, or access restrictions.
        Section 10: If Upwork displays verification, STOP and notify user.
        """
        current_url = page.url.lower()

        # 1. Login redirect handling
        if "/account-security/login" in current_url or "/ab/account-security/login" in current_url:
            if not settings.headless and not self.connected_via_cdp:
                print("\n" + "=" * 65)
                print(" [ACTION REQUIRED] UPWORK LOGIN REQUIRED")
                print(" Please log into your Upwork account in the opened Chrome browser window.")
                print(" Once you log in, the collector will automatically proceed!")
                print(" Waiting up to 120 seconds...")
                print("=" * 65 + "\n")
                logger.warning("Upwork login required. Waiting for user to complete login in opened window...")

                for _ in range(60):
                    time.sleep(2)
                    cur = page.url.lower()
                    if "/account-security/login" not in cur and "/ab/account-security/login" not in cur:
                        logger.info(f"User login detected! Current URL: {page.url}. Resuming collection.")
                        time.sleep(3)
                        return

            msg = (
                "Upwork redirected to login page. Authorized session required. "
                "Halting automated collection to protect account."
            )
            logger.error(msg)
            raise SecurityRestrictionError(msg)

        # 2. Check for Cloudflare / CAPTCHA / bot challenge in title or body
        # Give transient Cloudflare challenge up to 50 seconds to auto-clear
        for _ in range(25):
            title = page.title().lower()
            if "just a moment" not in title and "security verification" not in title and "attention required" not in title:
                break
            logger.info("Cloudflare verification in progress... waiting for clearance (2s)...")
            time.sleep(2.0)

        title = page.title().lower()
        if "just a moment" in title or "security verification" in title or "attention required" in title:
            msg = f"Security verification detected in page title: '{page.title()}'. Halting collection."
            logger.error(msg)
            raise SecurityRestrictionError(msg)

        # 3. Cloudflare Rate Limit (Error 1015 / Access Denied) Self-Cooling Engine
        try:
            content = page.content().lower()
        except Exception:
            content = ""

        if "error 1015" in content or "you are being rate limited" in content or "access denied | www.upwork.com" in title:
            logger.warning("[RATE LIMIT DETECTED] Cloudflare Error 1015 encountered! Activating protective cooldown for 90s...")
            for remaining in range(90, 0, -15):
                logger.info(f"Cooling down IP connection... {remaining}s remaining before retry.")
                time.sleep(15)
            # Attempt recovery reload
            try:
                page.reload(wait_until="domcontentloaded", timeout=20000)
                time.sleep(3)
                content = page.content().lower()
                title = page.title().lower()
            except Exception as e:
                logger.debug(f"Reload during cooldown note: {e}")

            if "error 1015" in content or "you are being rate limited" in content or "access denied" in title:
                msg = "Cloudflare Error 1015 rate limit is still active after cooldown. Halting to safeguard account."
                logger.error(msg)
                raise SecurityRestrictionError(msg)
            else:
                logger.info("Cloudflare rate limit cleared successfully! Resuming collection.")
                return

        if "cf-turnstile" in content or "g-recaptcha" in content or "bot detection" in content:
            # Check if it's transient
            time.sleep(2.0)
            try:
                content = page.content().lower()
            except Exception:
                content = ""
            if "cf-turnstile" in content or "g-recaptcha" in content:
                msg = "CAPTCHA / Bot verification widget detected in DOM. Halting collection immediately."
                logger.error(msg)
                raise SecurityRestrictionError(msg)

        if "unusual activity" in content or "rate limit exceeded" in content:
            msg = "Rate limit or unusual activity message displayed by Upwork. Halting collection."
            logger.error(msg)
            raise SecurityRestrictionError(msg)

    def close(self):
        """Gracefully closes resources without killing external user browser."""
        try:
            if self.new_tab and self.page:
                try:
                    self.page.close()
                except Exception:
                    pass
            elif not self.connected_via_cdp:
                if self.page:
                    self.page.close()
                if self.context:
                    self.context.close()
            if self.browser and not self.connected_via_cdp:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception as e:
            logger.debug(f"Error during browser teardown: {e}")
