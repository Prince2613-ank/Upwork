"""
Section 5 & 6: Client's Recent History and Review Expansion Parser.
Extracts every contract item from "Client's recent history", capturing both
client-to-freelancer and freelancer-to-client feedback with full un-truncated text.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup, Tag
from collector.models.schema import ClientHistoryItem


def clean_review_text(text: str) -> str:
    """Removes trailing "...more", "Show more", or button text from extracted reviews."""
    if not text:
        return ""
    # Remove "...more", "...less", "more", "less" at end of string
    cleaned = re.sub(r"(\.\.\.|\u2026)?\s*(?:more|less|show\s+more|show\s+less)\s*$", "", text, flags=re.IGNORECASE).strip()
    return cleaned


def is_review_truncated(text: str) -> bool:
    """
    Detects if a review appears truncated:
    - ends with ellipsis (...) or unicode ellipsis (\u2026)
    - ends with trailing '...more' or similar
    - abrupt cut mid-sentence without closing punctuation
    """
    if not text:
        return False
    trimmed = text.strip()
    if trimmed.endswith("...") or trimmed.endswith("\u2026"):
        return True
    if re.search(r"(\.\.\.|\u2026)?\s*(?:more|read more)\s*$", trimmed, re.IGNORECASE):
        return True
    return False


def parse_history_item(item_el: Tag) -> ClientHistoryItem:
    """Parses an individual contract card from the Client History section."""
    raw_text = item_el.get_text(separator="\n").strip()
    item = ClientHistoryItem()

    # 1. Job Title & URL
    title_el = item_el.select_one("a[href^='/jobs/'], a[href*='www.upwork.com/jobs/'], h4 a, .job-title, [data-test='job-title']")
    if title_el:
        item.job_title = title_el.get_text().strip()
        href = title_el.get("href", "")
        if href.startswith("/"):
            item.job_url = f"https://www.upwork.com{href}".split("?")[0]
        else:
            item.job_url = href.split("?")[0]
    else:
        # Fallback first strong or heading
        h_el = item_el.select_one("h4, strong, .air3-line-clamp-1")
        h_text = h_el.get_text().strip() if h_el else ""
        
        # If the text looks like a price or duration, it's not the title
        if h_text and not re.search(r'\$|€|£|/hr|hrs?\s*@|billed', h_text, re.IGNORECASE):
            item.job_title = h_text
        else:
            # Fallback to the very first line of text in the container
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            if lines:
                item.job_title = lines[0]

    # 2. Date and Duration
    # Format: "May 2024 - Jun 2024" or "Sep 2023 - Present"
    m_date = re.search(r"([A-Za-z]{3,9}\s+\d{4}\s*-\s*(?:[A-Za-z]{3,9}\s+\d{4}|Present))", raw_text)
    if m_date:
        item.date = m_date.group(1).strip()
    else:
        date_el = item_el.select_one("[data-test='contract-date'], time")
        if date_el:
            item.date = date_el.get_text().strip()

    m_dur = re.search(r"(\d+\s*(?:hours?|hrs?|days?|months?|weeks?))", raw_text, re.IGNORECASE)
    if m_dur:
        item.duration = m_dur.group(1).strip()

    # 3. Payment Type & Amount
    # Format: "Fixed-price $250.00" or "$35.00/hr"
    m_fixed = re.search(r"fixed[- ]price\s*:?\s*\$([\d,]+(?:\.\d+)?)", raw_text, re.IGNORECASE)
    m_hourly = re.search(r"\$([\d,]+(?:\.\d+)?)\s*(?:\/hr|hourly)", raw_text, re.IGNORECASE)

    if m_fixed:
        item.payment_type = "Fixed-price"
        item.amount = f"${m_fixed.group(1)}"
    elif m_hourly:
        item.payment_type = "Hourly"
        item.amount = f"${m_hourly.group(1)}/hr"
    else:
        # General dollar search
        m_amt = re.search(r"\$([\d,]+(?:\.\d+)?)", raw_text)
        if m_amt:
            item.amount = f"${m_amt.group(1)}"
            if "hourly" in raw_text.lower():
                item.payment_type = "Hourly"
            else:
                item.payment_type = "Fixed-price"

    # 4. Rating
    rating_el = item_el.select_one("[data-test='star-rating'], .rating")
    if rating_el:
        item.rating = rating_el.get_text().strip()
    else:
        m_rat = re.search(r"(\d\.\d{1,2})\s*(?:of 5|\/5|\bstars?\b)", raw_text, re.IGNORECASE)
        if m_rat:
            item.rating = m_rat.group(1)

    # 5. Freelancer Name
    # Often labeled "Freelancer: John Doe" or displayed in a user link
    fl_el = item_el.select_one("a[href*='/freelancers/'], [data-test='freelancer-name'], .freelancer-name")
    if fl_el:
        item.freelancer_name = fl_el.get_text().strip()
    else:
        m_fl = re.search(r"(?:To freelancer|Freelancer):\s*([^\n·]+)", raw_text, re.IGNORECASE)
        if m_fl:
            item.freelancer_name = m_fl.group(1).strip()

    # 6. Strictly Freelancer's Review for the Client Only
    # Upwork contract history items display two parts:
    #   Part 1: The freelancer's rating & review evaluating the CLIENT.
    #   Part 2: "To freelancer: <Name>" with the client's review evaluating the FREELANCER.
    # We strictly extract Part 1 (freelancer evaluating client) and discard Part 2.
    freelancer_review_text = ""

    # Primary path: .main container with structured child divs
    main_el = item_el.select_one('.main') or item_el
    child_divs = [c for c in main_el.children if getattr(c, 'name', None) == 'div']
    
    for c in child_divs:
        c_text = c.get_text(" ", strip=True)
        if "to freelancer" in c_text.lower():
            # This is the client evaluating the freelancer - DISCARD
            continue

        # Look for the freelancer's feedback comment span
        trunc_span = c.select_one('span[id^="air3-truncation-"]')
        if trunc_span:
            for btn in trunc_span.find_all(["button", "a"], string=re.compile(r"more|less", re.I)):
                btn.decompose()
            t = trunc_span.get_text(" ", strip=True)
            if t:
                freelancer_review_text = t
                break
        elif "no feedback given" in c_text.lower():
            freelancer_review_text = "No feedback given"
            break

    # Fallback path if not found in child divs:
    if not freelancer_review_text:
        # Check all air3-truncation spans, ignoring those inside 'to freelancer'
        for sp in item_el.select('span[id^="air3-truncation-"]'):
            is_to_fl = sp.find_parent(lambda tag: "to freelancer" in tag.get_text().lower() if getattr(tag, 'name', None) == 'div' else False)
            if not is_to_fl:
                for btn in sp.find_all(["button", "a"], string=re.compile(r"more|less", re.I)):
                    btn.decompose()
                t = sp.get_text(" ", strip=True)
                if t:
                    freelancer_review_text = t
                    break

    # Fallback path for regex labels or older markup:
    if not freelancer_review_text:
        m_to_cl = re.search(r"(?:Feedback to client|Freelancer's feedback):\s*\"?([^\"]+?)\"?(?=\n|Feedback to freelancer|To freelancer|$)", raw_text, re.IGNORECASE)
        if m_to_cl:
            freelancer_review_text = m_to_cl.group(1).strip()
        elif "no feedback given" in raw_text.lower():
            freelancer_review_text = "No feedback given"

    if not freelancer_review_text or freelancer_review_text == "No feedback given":
        freelancer_review_text = ""

    cleaned_feedback = clean_review_text(freelancer_review_text)
    item.feedback = cleaned_feedback
    truncated = is_review_truncated(freelancer_review_text)
    item.feedback_full = not truncated if (cleaned_feedback and cleaned_feedback != "No feedback given") else False

    return item


def parse_client_history(container_or_html: Any) -> List[ClientHistoryItem]:
    """Extracts all history items from Client's Recent History section."""
    if isinstance(container_or_html, str):
        soup = BeautifulSoup(container_or_html, "html.parser")
    elif isinstance(container_or_html, Tag):
        soup = container_or_html
    else:
        return []

    sec = soup.select_one(
        "[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history"
    )
    if not sec:
        # Fallback by searching for section headers
        for s in soup.find_all(['section', 'div', 'article']):
            h = s.find(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong'])
            if h and ("recent history" in h.get_text().lower() or "client history" in h.get_text().lower()):
                sec = s
                break
                
    if not sec:
        # If no client history section exists on the page, the client has 0 reviews!
        return []
        
    target = sec
    items = target.select('div.item[data-cy="job"]')

    if not items:
        items = target.select(
            "[data-test='history-item'], [data-test='contract-card'], .up-card-sub-section, .history-item, li.air3-card-list-item, article, [data-ev-label='contract_history_item']"
        )

    if not items:
        # Fallback to general cards inside the history container
        items = target.select(".air3-card, div.up-card-section")

    results: List[ClientHistoryItem] = []
    for el in items:
        parsed = parse_history_item(el)
        # Guard against any marketing or login footer cards
        t_low = (parsed.job_title or "").lower()
        f_low = (parsed.feedback or "").lower()
        if "explore upwork" in t_low or "already have an account" in f_low or "log in" in f_low or "sign up" in f_low:
            continue
        if parsed.job_title or parsed.feedback or parsed.amount:
            results.append(parsed)

    return results
