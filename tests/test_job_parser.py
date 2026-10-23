import pytest
from parsers.job_parser import parse_job_posting_page, extract_job_id_from_url, parse_budget_details

SAMPLE_JOB_HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Senior Python Engineer - Upwork</title>
</head>
<body>
    <article data-job-id="~01987654321fedcba">
        <header>
            <h1 data-test="job-title">Senior Python Data Pipeline Engineer</h1>
            <div data-test="posted-on" datetime="2026-09-18T10:00:00Z">Posted 2 days ago</div>
            <div data-test="job-type">$65.00 - $85.00 /hr</div>
            <div data-test="experience-level">Expert</div>
            <div data-test="duration">3 to 6 months</div>
        </header>

        <section class="description-section">
            <h3>Job Description</h3>
            <div data-test="job-description-text">
                <p>We need an experienced Python developer to build robust data pipelines.</p>
                <p>You must have deep familiarity with Playwright, Pydantic, and Snowflake.</p>
                <button>Less</button>
            </div>
        </section>

        <section class="skills-section">
            <span data-test="skill">Python</span>
            <span data-test="skill">Playwright</span>
            <span data-test="skill">PostgreSQL</span>
        </section>

        <section id="about-client" data-test="about-client">
            <div>Payment method verified</div>
            <div>4.95 of 5 stars (24 reviews)</div>
            <div>Location: United States</div>
            <div>$120K+ total spent</div>
            <div>35 jobs posted, 80% hire rate, 3 active jobs</div>
            <div>Member since Feb 10, 2020</div>
        </section>

        <section id="client-history" data-test="client-history">
            <li data-test="client-history-item">
                <h4 data-test="contract-title">Cloud Infrastructure Migration</h4>
                <div data-test="rating">5.0</div>
                <div class="feedback" data-test="freelancer-feedback">
                    <p data-test="review-full">Brilliant data engineer, delivered ahead of time.</p>
                </div>
            </li>
        </section>
    </article>
</body>
</html>
"""

def test_extract_job_id():
    url1 = "https://www.upwork.com/jobs/~01abc123def456"
    assert extract_job_id_from_url(url1) == "~01abc123def456"
    url2 = "https://www.upwork.com/freelance-jobs/applied/~01fedcba987654"
    assert extract_job_id_from_url(url2) == "~01fedcba987654"

def test_parse_budget_details():
    b_hourly = parse_budget_details("$30.00 - $60.00 /hr")
    assert b_hourly.type == "hourly"
    assert b_hourly.min_hourly == 30.0
    assert b_hourly.max_hourly == 60.0
    assert b_hourly.amount == 45.0

    b_fixed = parse_budget_details("Fixed price - Est. budget: $500.00")
    assert b_fixed.type == "fixed-price"
    assert b_fixed.amount == 500.0

def test_full_job_parsing():
    job = parse_job_posting_page(SAMPLE_JOB_HTML, job_url="https://www.upwork.com/jobs/~01987654321fedcba")
    assert job.job_id == "~01987654321fedcba"
    assert job.title == "Senior Python Data Pipeline Engineer"
    assert "Playwright, Pydantic, and Snowflake" in job.description
    assert "Less" not in job.description  # UI button stripped
    assert job.budget.type == "hourly"
    assert job.budget.min_hourly == 65.0
    assert job.budget.max_hourly == 85.0
    assert "Python" in job.skills
    assert "Playwright" in job.skills
    assert job.client.payment_verified is True
    assert job.client.location == "United States"
    assert job.client.total_spent == "$120K+ total spent"
    assert len(job.client_recent_history) == 1
    assert job.client_recent_history[0].full_review == "Brilliant data engineer, delivered ahead of time."
