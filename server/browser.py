"""Browser adapter: reuse authenticated sessions, never automate challenges."""
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.request import Request, urlopen

from collector.extraction.job_parser import parse_job_detail_page, extract_exact_publish_time
from collector.extraction.search_parser import parse_search_page_html
from collector.pagination.date_boundary import parse_upwork_date
from generate_standalone_report import restore_full_description_from_raw, restore_full_feedback_from_raw


class BrowserIssue(Exception):
    def __init__(self, kind, message, wait=0):
        super().__init__(message)
        self.kind, self.wait = kind, wait


def valid_url(url):
    parts = urlsplit(url)
    return parts.scheme == "https" and parts.hostname in ("upwork.com", "www.upwork.com") and not parts.username


def retry_after(value, reference=None):
    reference = reference or datetime.now(timezone.utc)
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, (parsedate_to_datetime(value) - reference).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return 900


def classify(status, url, title, text, headers=None):
    sample = (title + " " + text[:1500]).lower()
    if status == 429 or "error 1015" in sample or "you are being rate limited" in sample:
        raise BrowserIssue("cooldown", "Upwork rate limit; all collection paused", retry_after((headers or {}).get("retry-after")))
    if any(x in url.lower() for x in ("/login", "/account-security/", "/ab/account-security")):
        raise BrowserIssue("needs_login", "Upwork login is required")
    if any(x in sample for x in ("just a moment", "verify you are human", "attention required!", "performing security verification")):
        raise BrowserIssue("needs_verification", "Browser verification requires your attention")
    if status in (401, 403):
        raise BrowserIssue("needs_verification", "Access denied; inspect browser before resuming")
    if status in (404, 410):
        raise BrowserIssue("unavailable", "Job is no longer available")
    if status >= 500:
        raise BrowserIssue("temporary", "Upstream server error")


class BrowserSession:
    def __init__(self, endpoint):
        self.endpoint = endpoint

    def __enter__(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        try:
            self.browser = self.pw.chromium.connect_over_cdp(cdp_websocket(self.endpoint), timeout=15000)
            self.context = self.browser.contexts[0]
            self.page = next((p for p in self.context.pages if "upwork.com" in p.url), None)
            self.page = self.page or self.context.new_page()
            self.page.set_default_timeout(15000)
            self.page.set_default_navigation_timeout(45000)
            return self
        except Exception:
            self.pw.stop()
            raise

    def __exit__(self, *_):
        # Disconnect the client without closing the persistent browser/profile.
        self.pw.stop()

    def check(self, response=None):
        headers = response.headers if response else {}
        classify(response.status if response else 200, self.page.url,
                 self.page.title(), self.page.locator("body").inner_text(timeout=10000), headers)

    def navigate(self, url):
        if not valid_url(url):
            raise ValueError("Only HTTPS Upwork URLs are permitted")
        response = self.page.goto(url, wait_until="domcontentloaded", timeout=45000)
        self.check(response)
        return response

    def search(self, base, number):
        parts = urlsplit(base)
        params = dict(parse_qsl(parts.query))
        params.update(page=str(number), sort="recency", per_page="50")
        self.navigate(urlunsplit(parts._replace(query=urlencode(params))))
        self.page.locator("article, [data-test='JobTile'], .job-tile").first.wait_for(timeout=20000)
        self.check()
        raw = self.page.content()
        cards = parse_search_page_html(raw)
        for card in cards:
            if not valid_url(card["job_url"]):
                raise ValueError("Unexpected job URL in search results")
        if not cards:
            raise ValueError("No job cards parsed; refusing to claim complete coverage")
        return cards

    def detail(self, card, should_continue=lambda: True):
        self.navigate(card["job_url"])
        self.page.locator("h1, [data-test='job-title'], h4").first.wait_for(timeout=20000)
        deadline = time.monotonic() + 60
        expanded = 0
        history_complete = True
        # Bounded expansion of visible text/history controls. No challenge interaction.
        while time.monotonic() < deadline and expanded < 50 and should_continue():
            button = self.page.get_by_role("button", name=re.compile(r"^(?:more|view more|show more|load more)(?: reviews| feedback| jobs| history)?$", re.I))
            visible = next((b for b in button.all() if b.is_visible()), None)
            if visible is None:
                break
            before = self.page.content()
            visible.click(timeout=5000)
            self.check()
            expanded += 1
            if self.page.content() == before:
                history_complete = False
                break
        if time.monotonic() >= deadline or expanded >= 50:
            history_complete = False
        raw = self.page.content()
        job = parse_job_detail_page(raw, card["job_url"], card)
        data = job.model_dump(mode="json")
        from bs4 import BeautifulSoup
        data["posted_date_precision"] = "exact" if extract_exact_publish_time(BeautifulSoup(raw, "html.parser")) else "parsed_or_relative"
        data.pop("raw_html", None)
        description = data["job"].get("description", "")
        data["job"]["description"] = restore_full_description_from_raw(description, raw)
        for review in data.get("client_recent_history", []):
            review["feedback"] = restore_full_feedback_from_raw(review.get("feedback", ""), raw)
        data["history_expansion_complete"] = history_complete
        if not data["job"].get("description"):
            raise ValueError("Missing description; result has not been marked complete")
        return data, raw


def card_date(card, tz):
    raw = card.get("posted_time", "")
    if not raw:
        return None
    # Relative day/week/month labels cannot define exact midnight boundaries.
    # Include them as candidates; exact detail timestamps are used when available.
    dt, _ = parse_upwork_date(raw)
    return dt.astimezone(tz).date()


def cdp_websocket(endpoint):
    """Resolve CDP behind an internal TCP forwarder without Chromium Host rejection."""
    if endpoint.startswith(("ws://", "wss://")):
        return endpoint
    import json
    req = Request(endpoint.rstrip("/") + "/json/version", headers={"Host": "localhost"})
    with urlopen(req, timeout=5) as response:
        target = json.load(response)["webSocketDebuggerUrl"]
    external = urlsplit(endpoint)
    return urlunsplit(urlsplit(target)._replace(scheme="wss" if external.scheme == "https" else "ws", netloc=external.netloc))
