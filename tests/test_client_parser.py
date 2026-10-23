import pytest
from parsers.client_parser import parse_about_client, parse_numeric_spend

def test_parse_numeric_spend():
    assert parse_numeric_spend("$500 spent") == 500.0
    assert parse_numeric_spend("$3.5K spent") == 3500.0
    assert parse_numeric_spend("$120K+ total spent") == 120000.0
    assert parse_numeric_spend("$1.5M spent") == 1500000.0

def test_parse_about_client_html():
    snippet = """
    <div data-test="about-client">
        <div>Payment method verified</div>
        <div>5.0 of 5 stars (18 reviews)</div>
        <div>Location: Netherlands</div>
        <div>$3.5K+ total spent</div>
        <div>28 jobs posted, 75% hire rate, 2 active jobs</div>
        <div>Member since Jan 15, 2021</div>
        <div>$38.50 /hr avg hourly rate paid, 450 hours</div>
    </div>
    """
    client = parse_about_client(snippet)
    assert client.payment_verified is True
    assert client.rating == 5.0
    assert client.reviews_count == 18
    assert client.location == "Netherlands"
    assert client.total_spent == "$3.5K+ total spent"
    assert client.total_spent_amount == 3500.0
    assert client.jobs_posted == 28
    assert client.hire_rate == 75.0
    assert client.member_since == "Jan 15, 2021"
    assert client.hours_billed == 450
