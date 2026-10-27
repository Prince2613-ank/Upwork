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
from collector.extraction.review_parser import parse_client_history, is_review_truncated
from generate_standalone_report import restore_full_description_from_raw, restore_full_feedback_from_raw, extract_nuxt_strings


# Expands every visible "more" toggle on long reviews at once and returns how many it clicked.
TRUNCATION_CLICK_JS = """root => {
  let clicked = 0;
  for (const b of root.querySelectorAll('button')) {
    const label = b.textContent.trim();
    const toggle = b.matches('.air3-truncation-btn, [data-ev-label="truncation_toggle"]');
    if (toggle && !b.dataset.flodataClicked && /^(more|show more|view more)( feedback| review)?$/i.test(label) && b.offsetParent !== null) {
      b.dataset.flodataClicked = '1'; b.click(); clicked++;
    }
  }
  return clicked;
}"""


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
    if any(x in sample for x in ("your account has been suspended", "your account is suspended", "account has been restricted", "account is blocked", "account has been blocked")):
        raise BrowserIssue("blocked", "Upwork account restriction requires account-owner action")
    if any(x in url.lower() for x in ("/login", "/account-security/", "/ab/account-security")):
        raise BrowserIssue("needs_login", "Upwork login is required")
    if any(x in sample for x in ("just a moment", "verify you are human", "attention required!", "performing security verification")):
        raise BrowserIssue("needs_verification", "Browser verification requires your attention")
    # A job-specific restriction is terminal for this URL, not a broken session.
    # Check before generic 403 handling: Upwork serves this page with either 200 or 403.
    if re.search(r"/(?:jobs|freelance-jobs/apply)/", urlsplit(url).path):
        message = re.sub(r"\s+", " ", (title + " " + text[:12000]).lower())
        if "this job is private" in message and (
                "only freelancers invited" in message or "access denied" in message):
            raise BrowserIssue("unavailable", "Private job: only invited freelancers can view it; skipped")
        if any(phrase in message for phrase in (
                "this job is no longer available", "this job has been removed",
                "this job has been deleted", "this job posting is no longer available")):
            raise BrowserIssue("unavailable", "Job removed or no longer available; skipped")
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

    def reset_page(self):
        """Clear a stuck tab without clearing the authenticated browser profile."""
        old = self.page
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)
        self.page.set_default_navigation_timeout(45000)
        try:
            old.close(run_before_unload=False)
        except Exception:
            pass

    def history_scope(self):
        scopes = self.page.locator("[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history")
        for scope in scopes.all():
            if scope.is_visible():
                return scope
        heading = self.page.get_by_role("heading", name=re.compile(r"(?:client.*)?recent history|client history", re.I))
        if heading.count():
            # The heading sits in a header strip; the review list and "View more" are siblings in the enclosing card.
            for path in ("xpath=ancestor::div[contains(concat(' ', normalize-space(@class), ' '), ' air3-card ')][1]",
                         "xpath=ancestor::section[1]"):
                scope = heading.first.locator(path)
                if scope.count() and scope.is_visible():
                    return scope
        return None

    def click_and_wait(self, button, scope):
        from playwright.sync_api import expect
        before = scope.inner_text(timeout=5000)
        button.click(timeout=5000)
        expect(scope).not_to_have_text(before, timeout=6000)
        self.check()

    @staticmethod
    def history_item_count(scope):
        return scope.evaluate("""el => el.querySelectorAll(
            'div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], [data-ev-label="contract_history_item"]').length""")

    @staticmethod
    def history_signature(scope):
        return scope.evaluate("""el => Array.from(el.querySelectorAll(
            'div.item[data-cy="job"], [data-test="history-item"], [data-test="contract-card"], [data-ev-label="contract_history_item"]'))
            .map(item => item.textContent.trim()).filter(Boolean).join('\\n')""")

    def collect_history(self, should_continue):
        """Expand text and traverse history pages, with bounded work and coverage proof."""
        from collector.storage.central import merge_data
        deadline, pages, snapshots, seen = time.monotonic() + 150, [], [], set()
        all_reviews, complete, expected = [], True, None
        self.history_expected = None
        scope = self.history_scope()
        if scope is None:
            try:
                # Real pages often hydrate an h5 heading instead of using a data-test attribute.
                # Waiting only for the attribute burned the full timeout even after history appeared.
                section = self.page.locator("[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history")
                heading = self.page.get_by_role('heading', name=re.compile(r'(?:client.*)?recent history|client history', re.I))
                section.or_(heading).first.wait_for(timeout=10000)
            except Exception:
                self.check()
            scope = self.history_scope()
            if scope is None:
                return [], False, snapshots
        label = scope.inner_text(timeout=5000)[:250]
        match = re.search(r"(?:recent history|client history)\s*\((\d+)\)", label, re.I)
        if match:
            expected = int(match.group(1))
        self.history_expected = expected
        while len(pages) < 50 and time.monotonic() < deadline and should_continue():
            scope = self.history_scope()
            if scope is None:
                complete = False
                break
            if time.monotonic() >= deadline or not should_continue():
                complete = False
                break
            # One batch click per page of results: a client with 50 reviews would otherwise need 50 slow single clicks.
            # Text completeness is still verified per review below (feedback_full / truncation check).
            if scope.evaluate(TRUNCATION_CLICK_JS):
                self.page.wait_for_timeout(400)
            try:
                raw = scope.evaluate("el => el.outerHTML")
            except Exception:
                raw = self.page.content()
            snapshots.append(raw)
            parsed = [r.model_dump(mode="json") for r in parse_client_history(raw)]
            fingerprint = tuple((r.get("job_title"), r.get("date"), r.get("freelancer_name"), r.get("amount")) for r in parsed)
            if fingerprint in seen:
                complete = False
                break
            seen.add(fingerprint)
            pages.append(fingerprint)
            nuxt_raw = self.page.content() if any(is_review_truncated(r.get('feedback', '')) for r in parsed) else ''
            nuxt_strings = extract_nuxt_strings(nuxt_raw) if nuxt_raw else []
            for review in parsed:
                feedback = restore_full_feedback_from_raw(review.get("feedback", ""), nuxt_raw or raw, nuxt_strings=nuxt_strings)
                review.update(feedback=feedback, feedback_full=bool(feedback and not is_review_truncated(feedback)),
                              direction="freelancer_to_client")
            all_reviews = merge_data({"client_recent_history": all_reviews}, {"client_recent_history": parsed})["client_recent_history"]
            def next_control():
                more = scope.get_by_role("button", name=re.compile(r"^(?:load|view|show) more(?: history| contracts| jobs| reviews)?$", re.I))
                next_buttons = scope.get_by_role("button", name=re.compile(r"^(?:next|next page|next history page)$", re.I))
                next_links = scope.get_by_role("link", name=re.compile(r"^(?:next|next page)$", re.I))
                # Upwork's "View more" is <a href="javascript:">, so match by text on links and buttons, not by role.
                view_more = scope.locator("a, button").filter(has_text=re.compile(r"^\s*(?:load|view|show) more\s*$", re.I))
                return next((b for b in [*next_buttons.all(), *next_links.all(), *more.all(), *view_more.all()]
                             if b.is_visible() and b.is_enabled() and b.get_attribute("aria-disabled") != "true"), None)

            button = next_control()
            if button is None:
                # The link can be hidden while Upwork is still loading the next batch, so only stop once the list stops growing.
                before_wait = self.history_item_count(scope)
                if expected is not None and before_wait >= expected:
                    break  # The page already contains every contract promised by its heading.
                self.page.wait_for_timeout(2000)
                button = next_control()
                if button is None:
                    if self.history_item_count(scope) == before_wait:
                        break
                    continue  # Late items arrived: parse them on the next pass.
            before_click = self.history_signature(scope)
            try:
                self.click_and_wait(button, scope)
            except Exception:
                self.check()
                complete = False
                break
            # Pagination can replace a page with the same number of contracts.
            # Wait for changed contract content, not only a larger item count.
            grow_deadline = time.monotonic() + 10
            while time.monotonic() < grow_deadline:
                current = self.history_signature(scope)
                if current and current != before_click:
                    break
                self.page.wait_for_timeout(250)
        else:
            complete = False
        if expected is not None and len(all_reviews) < expected:
            complete = False
        if not should_continue():
            complete = False
        return all_reviews, complete, snapshots

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
        try:
            self.page.locator("h1, [data-test='job-title'], h4").first.wait_for(timeout=20000)
        except Exception:
            # The SPA may render an error only after the initial navigation response.
            self.check()
            raise
        self.check()
        description_full = True
        description_scope = self.page.locator("[data-test='job-description-text'], [data-test='Description'], [data-test='job-description']")
        if description_scope.count():
            scope = description_scope.first
            buttons = scope.get_by_role("button", name=re.compile(r"^(?:more|view more|show more)$", re.I))
            for button in buttons.all()[:5]:
                if button.is_visible() and should_continue():
                    try:
                        self.click_and_wait(button, scope)
                    except Exception:
                        self.check()
                        description_full = False
        history, history_complete, snapshots = self.collect_history(should_continue)
        self.check()
        raw = self.page.content()
        job = parse_job_detail_page(raw, card["job_url"], card, include_history=False)
        data = job.model_dump(mode="json")
        from bs4 import BeautifulSoup
        data["posted_date_precision"] = "exact" if extract_exact_publish_time(BeautifulSoup(raw, "html.parser")) else "parsed_or_relative"
        data.pop("raw_html", None)
        description = data["job"].get("description", "")
        data["job"]["description"] = restore_full_description_from_raw(description, raw)
        data["client_recent_history"] = history
        data["history_expansion_complete"] = history_complete
        data["history_expected"] = getattr(self, "history_expected", None)
        data["description_full"] = description_full and not data["job"]["description"].strip().endswith(("...", "…"))
        data["extraction_status"]["full_reviews"] = bool(history) and all(r["feedback_full"] for r in history if r.get("feedback"))
        return data, raw + "\n<!-- Captured history pages -->\n" + "\n".join(snapshots[:-1])


def card_date(card, tz):
    raw = card.get("posted_time", "")
    if not raw:
        return None
    # Relative day/week/month labels cannot define exact midnight boundaries.
    # Include them as candidates; exact detail timestamps are used when available.
    dt, _ = parse_upwork_date(raw)
    return dt.astimezone(tz).date()


def card_day_exact(card):
    """Upwork's 'yesterday' / 'N days ago' follow the UTC calendar day, so in a UTC window they are exact."""
    return bool(re.search(r"yesterday|\b\d+\s*days?\s*ago", card.get("posted_time", "").lower()))


def card_exact_time(card, tz):
    """Posting time for minute/hour labels, which are precise to about an hour; None for coarser labels."""
    raw = card.get("posted_time", "")
    if not re.search(r"(?:just now|moments? ago|\d+\s*(?:minute|min|hour|hr)s?\s*ago)", raw.lower()):
        return None
    return parse_upwork_date(raw)[0].astimezone(tz)


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
