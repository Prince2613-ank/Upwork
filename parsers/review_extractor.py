"""
Review extractor for Upwork client recent history items.
Ensures reviews are fully expanded, un-truncated, and cleaned of UI artifacts.
"""

import re
from typing import Tuple, Optional
from bs4 import BeautifulSoup
from .truncation_detector import detect_truncation


def clean_review_text(raw_text: str) -> str:
    """
    Cleans expanded review text by removing UI artifacts like trailing 'Less', 'More',
    multiple whitespace, and leading/trailing quotes while preserving the complete body.
    """
    if not raw_text:
        return ""

    text = raw_text.strip()

    # Remove UI toggle suffixes e.g. " Less" or " More" added by toggle buttons
    text = re.sub(r"\s+(Less|More|less|more)$", "", text).strip()

    # Normalize internal multiple whitespace/newlines
    text = re.sub(r"\s+", " ", text).strip()

    # If surrounded by symmetrical quotes, strip them cleanly
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        if len(text) >= 2:
            text = text[1:-1].strip()

    return text


def extract_review_from_html(review_container_html: str) -> Tuple[str, bool, str]:
    """
    Extracts review text from an HTML snippet (e.g. from client history card).
    Prioritizes full/expanded elements over truncated spans.
    Returns:
        (full_review_text, is_truncated, truncation_reason)
    """
    if not review_container_html:
        return "", False, "No review HTML provided"

    soup = BeautifulSoup(review_container_html, "html.parser")

    # 1. Look for full text attribute or un-clamped container
    full_text_el = soup.select_one(
        "[data-test='review-full'], [data-full-text], .review-full-text, .air3-truncation-content"
    )
    if full_text_el:
        if full_text_el.get("data-full-text"):
            candidate = full_text_el["data-full-text"]
        else:
            candidate = full_text_el.get_text()
    else:
        # Fallback to general review container or paragraph
        review_p = soup.select_one(
            "[data-test='review-comment'], [data-test='feedback-comment'], p.comment, .up-review-text, p"
        )
        if review_p:
            # Remove any nested button elements like 'More' or 'Less' before taking text
            for btn in review_p.find_all(["button", "a"]):
                btn.decompose()
            candidate = review_p.get_text()
        else:
            candidate = soup.get_text()

    cleaned = clean_review_text(candidate)
    is_trunc, reason = detect_truncation(cleaned)
    return cleaned, is_trunc, reason
