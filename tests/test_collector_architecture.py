"""
Unit tests for the new collector architecture and all specification requirements.
"""

import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from collector.config.settings import settings
from collector.pagination.date_boundary import parse_upwork_date, get_cutoff_datetime, is_older_than_cutoff
from collector.extraction.search_parser import parse_search_card, parse_search_page_html
from collector.extraction.client_parser import parse_about_client
from collector.extraction.review_parser import parse_client_history, clean_review_text, is_review_truncated
from collector.extraction.job_parser import parse_job_detail_page, extract_full_description
from collector.storage.database import JobDatabase
from collector.storage.json_export import export_jobs_json, export_run_summary_json
from collector.storage.csv_export import export_jobs_csv, export_client_history_csv
from collector.checkpoint.checkpoint_manager import CheckpointManager
from collector.logging.logger import ErrorLogger
from collector.fixtures import generate_mock_search_page_html, generate_mock_job_detail_html, MOCK_JOBS_CATALOG
from collector.main import CollectorEngine


def test_search_card_parser():
    html = generate_mock_search_page_html()
    cards = parse_search_page_html(html)
    assert len(cards) == 3
    card1 = cards[0]
    assert card1["job_id"] == "~01dutch20comic001"
    assert "Dutch -> English" in card1["job_title"]
    assert card1["payment_verified"] is True
    assert card1["client_location"] == "Netherlands"
    assert card1["client_total_spent"] == "$3K+ spent"
    assert card1["client_rating"] == "5.0"
    assert len(card1["required_skills"]) > 0


def test_job_parser_full_description_and_status():
    cat = MOCK_JOBS_CATALOG[0]
    detail_html = generate_mock_job_detail_html(
        job_id=cat["job_id"],
        title=cat["title"],
        location=cat["location"],
        posted_raw=cat["posted_raw"],
        budget_raw=cat["budget_raw"],
        experience=cat["experience"],
        skills=cat["skills"],
        description=cat["description"],
        client_spend=cat["client_spend"],
        client_rating=cat["client_rating"],
        history_count=cat["history_count"],
    )

    job = parse_job_detail_page(detail_html, job_url=f"https://www.upwork.com/jobs/{cat['job_id']}")
    assert job.job_id == "~01dutch20comic001"
    assert "translate a 20-page Dutch comic" in job.job.description
    # Section 7: Verify no "...more" button artifact remains
    assert not job.job.description.endswith("...more")
    assert not job.job.description.endswith("More")
    assert "\n\n" in job.job.description  # Paragraph boundaries preserved

    # Section 14: Extraction Status
    assert job.extraction_status.job_details is True
    assert job.extraction_status.description is True
    assert job.extraction_status.about_client is True
    assert job.extraction_status.recent_history is True


def test_client_parser_fields():
    cat = MOCK_JOBS_CATALOG[0]
    detail_html = generate_mock_job_detail_html(
        job_id=cat["job_id"],
        title=cat["title"],
        location=cat["location"],
        posted_raw=cat["posted_raw"],
        budget_raw=cat["budget_raw"],
        experience=cat["experience"],
        skills=cat["skills"],
        description=cat["description"],
        client_spend=cat["client_spend"],
        client_rating=cat["client_rating"],
        history_count=cat["history_count"],
    )
    client = parse_about_client(detail_html)
    assert client.payment_verified is True
    assert client.rating == "5.0"
    assert client.total_spent == "$3K+ spent"
    assert client.location == "Netherlands"
    assert client.jobs_posted == "28"
    assert client.hire_rate == "75%"
    assert client.active_hires == "1"
    assert client.member_since == "Jan 15, 2021"


def test_review_parser_and_expansion():
    cat = MOCK_JOBS_CATALOG[0]
    detail_html = generate_mock_job_detail_html(
        job_id=cat["job_id"],
        title=cat["title"],
        location=cat["location"],
        posted_raw=cat["posted_raw"],
        budget_raw=cat["budget_raw"],
        experience=cat["experience"],
        skills=cat["skills"],
        description=cat["description"],
        client_spend=cat["client_spend"],
        client_rating=cat["client_rating"],
        history_count=cat["history_count"],
    )
    history = parse_client_history(detail_html)
    assert len(history) == 8
    assert "Past Contract Milestone" in history[0].job_title
    assert history[0].amount == "$250.00"
    assert history[0].payment_type == "Fixed-price"
    assert history[0].rating == "5.0"
    assert "freelancer did an extraordinary job" in history[0].feedback
    assert not history[0].feedback.endswith("more")


def test_date_cutoff_boundary():
    now = datetime(2026, 9, 20, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = get_cutoff_datetime(1, reference_time=now)
    assert cutoff.year == 2026
    assert cutoff.month == 8
    assert cutoff.day == 20

    # Recent job
    job_recent = now - timedelta(days=5)
    assert is_older_than_cutoff(job_recent, cutoff) is False

    # Older job
    job_old = now - timedelta(days=35)
    assert is_older_than_cutoff(job_old, cutoff) is True


def test_checkpoint_manager_roundtrip(tmp_path):
    mgr = CheckpointManager(output_dir=tmp_path)
    mgr.save_checkpoint(
        last_completed_page=3,
        processed_job_ids=["~01abc", "~02def"],
        cutoff_date="2026-08-20T00:00:00+00:00",
        last_processed_job="~02def",
        status="paused",
    )

    ckpt = mgr.load_checkpoint()
    assert ckpt is not None
    assert ckpt.last_completed_page == 3
    assert ckpt.processed_job_ids == ["~01abc", "~02def"]
    assert ckpt.status == "paused"


def test_export_engines(tmp_path):
    engine = CollectorEngine(source_mode="mock")
    jobs = engine.run_test_3_jobs()
    assert len(jobs) == 3

    # Verify exports exist and are valid
    jobs_json = settings.output_path / "jobs.json"
    assert jobs_json.exists()
    with open(jobs_json, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert "scrape_run" in data
    assert "jobs" in data
    assert len(data["jobs"]) == 3

    # Verify Section 8 schema keys
    j0 = data["jobs"][0]
    assert "job_id" in j0
    assert "job_url" in j0
    assert "job" in j0
    assert "client" in j0
    assert "client_recent_history" in j0
    assert "extraction_status" in j0

    jobs_csv = settings.output_path / "jobs.csv"
    assert jobs_csv.exists()
    assert jobs_csv.stat().st_size > 0

    hist_csv = settings.output_path / "client_history.csv"
    assert hist_csv.exists()
    assert hist_csv.stat().st_size > 0

    summary_json = settings.output_path / "run_summary.json"
    assert summary_json.exists()
    with open(summary_json, "r", encoding="utf-8") as f:
        sdata = json.load(f)
    assert "pages_processed" in sdata
    assert "date_range" in sdata


def test_error_logger(tmp_path):
    el = ErrorLogger(output_dir=tmp_path)
    el.log_error("https://www.upwork.com/jobs/~failed001", "Timeout connecting to host", retry_count=2)
    assert len(el.errors) == 1
    err = el.errors[0]
    assert err["job_url"] == "https://www.upwork.com/jobs/~failed001"
    assert err["retry_count"] == 2
    assert "Timeout" in err["error"]
