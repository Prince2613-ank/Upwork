"""
Truncation detection and validation engine for Upwork client reviews.
"""

import re
from typing import Tuple


def detect_truncation(text: str) -> Tuple[bool, str]:
    """
    Audits review text for evidence of truncation, collapsed content, or ellipsis cutoff.
    Returns:
        (is_truncated: bool, reason: str)
    """
    if not text:
        return False, "Empty review text"

    cleaned = text.strip()

    # Pattern 1: Literal trailing ellipses
    if cleaned.endswith("...") or cleaned.endswith("…") or cleaned.endswith(".."):
        return True, "Ends with trailing ellipsis"

    # Pattern 2: Trailing "More", "... More", or "...more"
    if re.search(r"(\.\.\.|\…)?\s*(more|read more|view more)\s*$", cleaned, re.IGNORECASE):
        return True, "Ends with un-expanded 'More' control label"

    # Pattern 3: Trailing ellipsis before closing quote
    if re.search(r"(\.\.\.|\…)\s*[\"']$", cleaned):
        return True, "Ends with ellipsis inside quote"

    # Pattern 4: Internal un-expanded truncation marker (e.g. "text... More next")
    if re.search(r"\b\w+\.\.\.\s*(more|read more)\b", cleaned, re.IGNORECASE):
        return True, "Contains un-expanded inline '... More' marker"

    # Pattern 5: Incomplete mid-word cutoff followed by dots
    if re.search(r"[a-zA-Z]\.{2,}\s*$", cleaned):
        return True, "Word cut off with dots"

    return False, "Complete un-truncated review"
