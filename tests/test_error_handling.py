import pytest
from parsers.job_parser import parse_job_posting_page
from parsers.client_parser import parse_about_client
from parsers.date_parser import parse_upwork_date

def test_graceful_handling_empty_html():
    job = parse_job_posting_page("", job_url="https://www.upwork.com/jobs/~empty")
    assert job.job_id == "~empty"
    assert job.title == "Untitled Job Posting"
    assert job.description == ""
    assert job.skills == []
    assert job.client.payment_verified is None

def test_graceful_handling_malformed_client_info():
    malformed_text = "Some random text without structured client indicators"
    client = parse_about_client(malformed_text)
    assert client.location is None
    assert client.rating is None
    assert client.total_spent is None

def test_graceful_handling_unparseable_date():
    dt, iso = parse_upwork_date("completely_gibberish_date_string")
    assert dt is not None
    assert iso is not None
