"""
Date parsing and cutoff evaluation for Upwork job postings.
"""

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from dateutil import parser as dateutil_parser


def parse_upwork_date(
    date_str: str,
    reference_time: Optional[datetime] = None,
) -> Tuple[datetime, str]:
    """
    Parses Upwork's various date representations into a timezone-aware UTC datetime.
    Supports:
      - Relative strings: "Posted 4 minutes ago", "Posted 2 hours ago", "Posted 1 day ago",
                          "Posted 3 weeks ago", "Posted 1 month ago", "yesterday"
      - Absolute strings: "Posted Aug 25, 2026", "Sep 18, 2026 14:00 UTC", ISO strings
    Returns:
      (parsed_datetime_utc, iso_string)
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)

    cleaned = date_str.strip()
    # Strip common prefixes like "Posted ", "posted on ", etc.
    cleaned = re.sub(r"^(posted\s*(on|at)?\s*:?\s*)", "", cleaned, flags=re.IGNORECASE).strip()

    # Match relative patterns
    lower = cleaned.lower()

    if "just now" in lower or "moments ago" in lower:
        dt = reference_time
        return dt, dt.isoformat()

    if "yesterday" in lower:
        dt = reference_time - timedelta(days=1)
        return dt, dt.isoformat()

    # Check for "X minutes/hours/days/weeks/months ago"
    rel_match = re.search(r"(\d+)\s*(minute|min|hour|hr|day|week|month|year)s?\s*ago", lower)
    if rel_match:
        qty = int(rel_match.group(1))
        unit = rel_match.group(2)
        if "min" in unit:
            dt = reference_time - timedelta(minutes=qty)
        elif "hour" in unit or "hr" in unit:
            dt = reference_time - timedelta(hours=qty)
        elif "day" in unit:
            dt = reference_time - timedelta(days=qty)
        elif "week" in unit:
            dt = reference_time - timedelta(weeks=qty)
        elif "month" in unit:
            dt = reference_time - timedelta(days=qty * 30)
        elif "year" in unit:
            dt = reference_time - timedelta(days=qty * 365)
        else:
            dt = reference_time
        return dt, dt.isoformat()

    # Try standard dateutil parsing for absolute dates (e.g. "Aug 25, 2026", "2026-09-18T10:00:00Z")
    try:
        dt = dateutil_parser.parse(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt, dt.isoformat()
    except Exception:
        # Fallback to reference time if completely unparseable
        return reference_time, reference_time.isoformat()


def is_older_than_cutoff(job_datetime: datetime, cutoff_datetime: datetime) -> bool:
    """
    Returns True if job_datetime is strictly older (earlier) than cutoff_datetime.
    """
    if job_datetime.tzinfo is None:
        job_datetime = job_datetime.replace(tzinfo=timezone.utc)
    if cutoff_datetime.tzinfo is None:
        cutoff_datetime = cutoff_datetime.replace(tzinfo=timezone.utc)
    return job_datetime < cutoff_datetime


def get_cutoff_datetime(days_back: int = 30, reference_time: Optional[datetime] = None) -> datetime:
    """
    Computes the cutoff datetime: reference_time - days_back.
    """
    if reference_time is None:
        reference_time = datetime.now(timezone.utc)
    elif reference_time.tzinfo is None:
        reference_time = reference_time.replace(tzinfo=timezone.utc)
    return reference_time - timedelta(days=days_back)
