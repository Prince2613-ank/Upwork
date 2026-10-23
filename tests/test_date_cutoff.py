from datetime import datetime, timedelta, timezone
import pytest
from parsers.date_parser import parse_upwork_date, is_older_than_cutoff, get_cutoff_datetime

def test_parse_relative_dates():
    ref = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)

    dt1, iso1 = parse_upwork_date("Posted 4 minutes ago", reference_time=ref)
    assert dt1 == ref - timedelta(minutes=4)

    dt2, iso2 = parse_upwork_date("Posted 3 hours ago", reference_time=ref)
    assert dt2 == ref - timedelta(hours=3)

    dt3, iso3 = parse_upwork_date("Posted 5 days ago", reference_time=ref)
    assert dt3 == ref - timedelta(days=5)

    dt4, iso4 = parse_upwork_date("Posted 2 weeks ago", reference_time=ref)
    assert dt4 == ref - timedelta(weeks=2)

def test_date_cutoff_evaluation():
    ref = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = get_cutoff_datetime(days_back=30, reference_time=ref)
    # Cutoff is 2026-08-21 12:00:00

    # Job from 15 days ago (inside window)
    job_recent = ref - timedelta(days=15)
    assert not is_older_than_cutoff(job_recent, cutoff)

    # Job from 29 days ago (inside window)
    job_boundary = ref - timedelta(days=29)
    assert not is_older_than_cutoff(job_boundary, cutoff)

    # Job from 31 days ago (older than cutoff -> MUST STOP)
    job_old = ref - timedelta(days=31)
    assert is_older_than_cutoff(job_old, cutoff)

    # Job from 45 days ago (older than cutoff -> MUST STOP)
    job_very_old = ref - timedelta(days=45)
    assert is_older_than_cutoff(job_very_old, cutoff)
