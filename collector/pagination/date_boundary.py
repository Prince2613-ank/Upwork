"""
Date boundary and cutoff stopping engine for Upwork Collector.
Strictly implements rolling one-month date cutoff stopping condition (Section 1, Section 9).
"""

import re
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from dateutil.relativedelta import relativedelta


def get_cutoff_datetime(
    months: int = 1,
    days: int = 0,
    reference_time: Optional[datetime] = None,
) -> datetime:
    """
    Computes the exact date cutoff.
    If days > 0, uses days window (takes priority over months).
    e.g. days=2 → only fetch jobs from the last 2 days.
    e.g. months=1 → fetch jobs from the last 30 days.
    """
    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    if days > 0:
        return ref - timedelta(days=days)
    return ref - relativedelta(months=months)


def parse_upwork_date(
    date_str: str,
    reference_time: Optional[datetime] = None,
) -> Tuple[datetime, str]:
    """
    Parses relative Upwork timestamps ('4 minutes ago', '1 hour ago', '2 days ago', 'yesterday')
    or absolute date strings ('Sep 20, 2026', 'Aug 15, 2026') into a timezone-aware datetime
    and ISO 8601 string.
    """
    ref = reference_time or datetime.now(timezone.utc)
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    if not date_str:
        return ref, ref.isoformat()

    s = date_str.strip().lower()

    # Clean up prefixes like "posted"
    s = re.sub(r"^posted\s+", "", s)

    # 1. ISO format check
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        try:
            dt = datetime.fromisoformat(s.replace("z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt, dt.isoformat()
        except Exception:
            pass

    # 2. Relative times
    if "just now" in s or "moments ago" in s:
        return ref, ref.isoformat()

    m = re.search(r"(\d+)\s*(?:minute|min)s?\s*ago", s)
    if m:
        dt = ref - timedelta(minutes=int(m.group(1)))
        return dt, dt.isoformat()

    m = re.search(r"(\d+)\s*(?:hour|hr)s?\s*ago", s)
    if m:
        dt = ref - timedelta(hours=int(m.group(1)))
        return dt, dt.isoformat()

    if "yesterday" in s:
        dt = ref - timedelta(days=1)
        return dt, dt.isoformat()

    m = re.search(r"(\d+)\s*days?\s*ago", s)
    if m:
        dt = ref - timedelta(days=int(m.group(1)))
        return dt, dt.isoformat()

    m = re.search(r"(\d+)\s*weeks?\s*ago", s)
    if m:
        dt = ref - timedelta(weeks=int(m.group(1)))
        return dt, dt.isoformat()

    m = re.search(r"(\d+)\s*months?\s*ago", s)
    if m:
        dt = ref - relativedelta(months=int(m.group(1)))
        return dt, dt.isoformat()

    # 3. Absolute dates e.g. "Aug 20, 2026" or "Sep 4"
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%b %d", "%B %d"):
        try:
            parsed = datetime.strptime(s, fmt)
            year = parsed.year if "%Y" in fmt else ref.year
            dt = datetime(year, parsed.month, parsed.day, tzinfo=timezone.utc)
            if dt > ref:
                dt = dt.replace(year=year - 1)
            return dt, dt.isoformat()
        except ValueError:
            continue

    # Fallback to current time
    return ref, ref.isoformat()


def is_older_than_cutoff(job_dt: datetime, cutoff_dt: datetime) -> bool:
    """Returns True if the job was posted strictly prior to the cutoff date."""
    if job_dt.tzinfo is None:
        job_dt = job_dt.replace(tzinfo=timezone.utc)
    if cutoff_dt.tzinfo is None:
        cutoff_dt = cutoff_dt.replace(tzinfo=timezone.utc)
    return job_dt < cutoff_dt
