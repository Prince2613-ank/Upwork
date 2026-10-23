"""
Parser for Upwork 'Client's Recent History' contract records.
"""

import re
from typing import List, Dict, Any
from bs4 import BeautifulSoup
from models.schema import ClientRecentHistoryItem
from .review_extractor import extract_review_from_html, clean_review_text


def parse_history_item_html(item_el) -> ClientRecentHistoryItem:
    """
    Parses a single past contract DOM element or BeautifulSoup tag.
    """
    history_item = ClientRecentHistoryItem()
    raw_text = item_el.get_text(separator="\n").strip()
    history_item.raw_text = raw_text

    # 1. Job Title
    title_el = item_el.select_one(
        "[data-test='contract-title'], [data-test='job-title'], h4, .up-history-title, a"
    )
    if title_el:
        history_item.job_title = title_el.get_text().strip()
    else:
        # Fallback to first non-empty line
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        if lines:
            history_item.job_title = lines[0]

    # 2. Date Range
    # Examples: "May 2024 - Jun 2024", "Jan 2023 - Present", "Aug 15, 2024"
    date_match = re.search(
        r"([A-Za-z]{3,9}\s+\d{4}\s*-\s*(?:[A-Za-z]{3,9}\s+\d{4}|Present|present))",
        raw_text,
    )
    if date_match:
        history_item.date = date_match.group(1).strip()
    else:
        d2 = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", raw_text)
        if d2:
            history_item.date = d2.group(1).strip()

    # 3. Rating (0.0 - 5.0)
    rating_el = item_el.select_one("[data-test='rating'], .air3-rating-value, .up-rating")
    if rating_el:
        try:
            history_item.rating = float(rating_el.get_text().strip())
        except ValueError:
            pass
    if history_item.rating is None:
        r_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:of\s*5|\/5|\s*stars)", raw_text, re.IGNORECASE)
        if r_match:
            try:
                val = float(r_match.group(1))
                if 0.0 <= val <= 5.0:
                    history_item.rating = val
            except ValueError:
                pass

    # 4. Amount & Payment Type
    # Examples: "$500.00", "$45.00/hr (12 hrs)", "Fixed price $250"
    if re.search(r"hourly|\/hr", raw_text, re.IGNORECASE):
        history_item.payment_type = "Hourly"
        amt_match = re.search(r"(\$[\d,]+(?:\.\d+)?(?:\s*\/hr)?(?:\s*\([\d,]+\s*hrs?\))?)", raw_text, re.IGNORECASE)
        if amt_match:
            history_item.amount = amt_match.group(1).strip()
    elif re.search(r"fixed[- ]price", raw_text, re.IGNORECASE):
        history_item.payment_type = "Fixed-price"
        amt_match = re.search(r"(\$[\d,]+(?:\.\d+)?)", raw_text)
        if amt_match:
            history_item.amount = amt_match.group(1).strip()
    else:
        amt_match = re.search(r"(\$[\d,]+(?:\.\d+)?)", raw_text)
        if amt_match:
            history_item.amount = amt_match.group(1).strip()

    # 5. Freelancer Name
    # Often rendered as "To freelancer: John Doe" or "Freelancer: Jane Smith" or before feedback
    fl_match = re.search(r"(?:to\s+freelancer|freelancer):\s*([A-Za-z0-9\s\.\-]+?)(?=\n|$)", raw_text, re.IGNORECASE)
    if fl_match:
        history_item.freelancer = fl_match.group(1).strip()

    # 6. Complete Review Text
    # Priority: Extract from review container
    review_container = item_el.select_one(
        "[data-test='freelancer-feedback'], [data-test='feedback-comment'], .feedback-content, .up-review, [data-test='review']"
    )
    if review_container:
        full_rev, is_trunc, reason = extract_review_from_html(str(review_container))
        history_item.full_review = full_rev
        history_item.is_truncated = is_trunc
    else:
        # Check if there is quoted feedback in text
        quote_match = re.search(r'["“](.+?)["”]', raw_text, re.DOTALL)
        if quote_match:
            cleaned = clean_review_text(quote_match.group(1))
            full_rev, is_trunc, reason = extract_review_from_html(f"<p>{cleaned}</p>")
            history_item.full_review = full_rev
            history_item.is_truncated = is_trunc

    return history_item


def parse_client_history(html_or_soup) -> List[ClientRecentHistoryItem]:
    """
    Parses all items in the 'Client's recent history' section.
    """
    if not html_or_soup:
        return []

    if isinstance(html_or_soup, str):
        soup = BeautifulSoup(html_or_soup, "html.parser")
    else:
        soup = html_or_soup

    items: List[ClientRecentHistoryItem] = []

    # Select all contract history cards
    history_elements = soup.select(
        "[data-test='client-history-item'], [data-test='contract-history-item'], "
        ".up-client-history-item, .air3-slider-item, li.up-card-section, .history-item"
    )

    if not history_elements:
        # Fallback to general list items inside client history container
        container = soup.select_one("[data-test='client-history'], .client-history, #client-history")
        if container:
            history_elements = container.select("li, .card, div.border-bottom")

    for el in history_elements:
        item = parse_history_item_html(el)
        # Verify item has at least title or feedback
        if item.job_title or item.full_review or item.amount:
            items.append(item)

    return items
