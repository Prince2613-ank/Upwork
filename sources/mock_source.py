"""
Mock Data Source with realistic HTML fixtures for offline testing and verification.
Provides multi-page pagination, date-spaced jobs, full descriptions, client info,
and complete un-truncated reviews.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Tuple
from .base import BaseDataSource


def generate_mock_job_html(
    job_id: str,
    title: str,
    posted_dt: datetime,
    client_country: str,
    client_spend: str,
    client_rating: float,
    budget_str: str,
    description: str,
    skills: List[str],
    history_items: List[Dict[str, Any]],
) -> str:
    """
    Generates a realistic Upwork Job Details Drawer / Page HTML.
    """
    posted_iso = posted_dt.isoformat()
    # Relative label
    diff = datetime.now(timezone.utc) - posted_dt
    if diff.total_seconds() < 3600:
        posted_label = f"Posted {int(diff.total_seconds() // 60)} minutes ago"
    elif diff.total_seconds() < 86400:
        posted_label = f"Posted {int(diff.total_seconds() // 3600)} hours ago"
    else:
        days = diff.days
        if days == 1:
            posted_label = "Posted 1 day ago"
        elif days < 30:
            posted_label = f"Posted {days} days ago"
        else:
            posted_label = f"Posted {posted_dt.strftime('%b %d, %Y')}"

    skills_html = "\n".join(
        [f'<span data-test="skill" class="air3-token">{s}</span>' for s in skills]
    )

    history_html_list = []
    for item in history_items:
        trunc_attr = f' data-full-text="{item["review"]}"' if item.get("use_attr") else ""
        review_body = item["review"]
        history_html_list.append(
            f"""
            <li class="history-item" data-test="client-history-item">
                <h4 data-test="contract-title">{item['title']}</h4>
                <div class="meta">
                    <span class="date">{item['date']}</span>
                    <span data-test="rating">{item['rating']}</span>
                    <span class="amount">{item['amount']}</span>
                </div>
                <div class="freelancer-info">Freelancer: {item.get('freelancer', 'Top Rated Talent')}</div>
                <div class="feedback" data-test="freelancer-feedback"{trunc_attr}>
                    <p class="comment" data-test="review-full">{review_body}</p>
                </div>
            </li>
            """
        )
    history_html = "\n".join(history_html_list)

    return f"""<!DOCTYPE html>
<html>
<head>
    <title>{title} - Upwork</title>
    <link rel="canonical" href="https://www.upwork.com/jobs/{job_id}" />
</head>
<body>
    <article data-job-id="{job_id}">
        <header>
            <h1 data-test="job-title">{title}</h1>
            <div data-test="posted-on" datetime="{posted_iso}">{posted_label}</div>
            <div data-test="job-type">{budget_str}</div>
            <div data-test="experience-level">Intermediate</div>
            <div data-test="duration">1 to 3 months</div>
        </header>

        <section class="description-section">
            <h3>Job Description</h3>
            <div data-test="job-description-text" class="up-line-clamp-expanded">
                {description}
            </div>
        </section>

        <section class="skills-section">
            <h3>Skills and Expertise</h3>
            <div class="skills-container">
                {skills_html}
            </div>
        </section>

        <section id="about-client" data-test="about-client">
            <h3>About the client</h3>
            <div class="verification"><svg></svg> Payment method verified</div>
            <div class="rating">{client_rating} of 5 stars (18 reviews)</div>
            <div class="location">Location: {client_country}</div>
            <div class="spend">{client_spend} total spent</div>
            <div class="hire-stats">28 jobs posted, 75% hire rate, 2 active jobs</div>
            <div class="member-since">Member since Jan 15, 2021</div>
            <div class="hourly-avg">$38.50 /hr avg hourly rate paid, 450 hours</div>
        </section>

        <section id="client-history" data-test="client-history">
            <h3>Client's recent history</h3>
            <ul class="contracts-list">
                {history_html}
            </ul>
        </section>
    </article>
</body>
</html>
"""


class MockJobDataSource(BaseDataSource):
    """
    Simulated data source that serves 65+ realistic jobs across 2 pages,
    carefully date-spaced around the 30-day cutoff date (2026-09-20).
    """

    def __init__(self, reference_time: datetime = None):
        if reference_time is None:
            # Anchor to the current run date: 2026-09-20 14:30:00 UTC
            self.reference_time = datetime(2026, 9, 20, 14, 30, 0, tzinfo=timezone.utc)
        else:
            self.reference_time = reference_time
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._build_dataset()

    def _build_dataset(self):
        # We generate jobs spanning from Day 0 (today) back to Day 35.
        # Cutoff at Day 30 means jobs with Day > 30 should trigger stopping condition!
        titles_templates = [
            ("Dutch -> English Comic Translation & Manual Lettering - 20 Pages", ["Dutch to English Translation", "Adobe Illustrator", "Lettering"], "$25.00 fixed-price", "Netherlands", "$3.5K+ spent", 5.0),
            ("Senior Python & Cloud Data Pipeline Engineer", ["Python", "AWS", "Snowflake", "PostgreSQL", "ETL"], "$65.00 - $90.00 /hr", "United States", "$140K+ spent", 4.98),
            ("Market Intelligence Scraping & Data Extraction Pipeline", ["Python", "Playwright", "Web Scraping", "Data Normalization"], "$500.00 fixed-price", "United Kingdom", "$52K+ spent", 5.0),
            ("Full Stack Next.js & Supabase Enterprise Portal", ["React", "Next.js", "TypeScript", "Supabase", "Tailwind CSS"], "$45.00 - $70.00 /hr", "Canada", "$85K+ spent", 4.92),
            ("Healthcare B2B Lead Generation & Account Intelligence", ["Lead Generation", "Market Research", "Apollo.io", "Data Enrichment"], "$350.00 fixed-price", "Saudi Arabia", "$28K+ spent", 5.0),
            ("Power BI Financial Dashboard & DAX Modeling", ["Power BI", "DAX", "Financial Modeling", "SQL"], "$50.00 /hr", "Australia", "$95K+ spent", 5.0),
            ("FastAPI Backend Developer for Analytics Microservices", ["FastAPI", "Docker", "Redis", "REST API"], "$40.00 - $60.00 /hr", "Germany", "$31K+ spent", 4.89),
            ("Shopify Plus Integration & ERP Data Sync", ["Shopify", "Node.js", "GraphQL", "Webhooks"], "$800.00 fixed-price", "United States", "$220K+ spent", 5.0),
            ("LLM Evaluation & Prompt Engineering Specialist", ["Python", "Claude API", "LLM", "Prompt Engineering"], "$75.00 /hr", "Israel", "$64K+ spent", 5.0),
            ("B2B Sales Prospecting & Flodata Intelligence Campaign", ["Cold Outreach", "B2B Sales", "HubSpot", "Data Mining"], "$450.00 fixed-price", "Belgium", "$19K+ spent", 4.95),
        ]

        # Multi-paragraph rich descriptions satisfying "Description पूरी चाहिए"
        sample_descriptions = [
            """We are seeking a seasoned data extraction and market intelligence engineer to design and operate our competitive intelligence pipelines. Flodata Analytics tracks procurement shifts, public vendor transactions, and marketplace demand.

In this role, you will be responsible for:
- Constructing resilient data harvesting workflows with automated schema validation.
- Normalizing unstructured client requirements, job histories, and feedback records.
- Ensuring complete field capture without truncation, especially for nested feedback items.
- Establishing checkpointing and incremental synchronization so collection jobs can resume safely.

Requirements:
- Proven production experience in Python, Playwright/Puppeteer, and structured data serialization.
- Familiarity with robust JSON schema validation and export workflows.
- Strong commitment to data completeness and code quality.""",

            """We are expanding our B2B intelligence platform and need a dedicated specialist to collect, structure, and synthesize outsourcing transaction records.

The primary objective is analyzing enterprise client purchasing habits, identifying recurring technology acquisitions, and highlighting high-potential accounts for business development.

Responsibilities:
1. Extract complete job specifications, budget terms, and multi-year client feedback.
2. Maintain strict data integrity with zero data loss on extended text fields.
3. Validate datasets against strict quality criteria before delivering to analytics teams.

Please provide examples of previous structured data collection projects.""",

            """Looking for a skilled specialist to manage our market analysis workflow. We collect public marketplace listings to assess tech stack migration patterns.

Every record must include:
- Full job description text (no summaries or truncated previews).
- Complete About Client metrics (spend, rating, total jobs, hire rates).
- Historical contract reviews un-truncated for sentiment and vendor name extraction.

All work must be delivered as validated JSON and accompanying CSV exports with verifiable provenance.""",
        ]

        sample_reviews = [
            "Flodata and their engineering team did an extraordinary job on our enterprise ingestion pipeline. They delivered fully un-truncated data records, caught complex edge cases in our schemas, and maintained exceptional communication throughout. Highly recommended for any serious data engineering engagement!",
            "Outstanding work! Delivered clean, thoroughly tested Python modules with full test coverage and automated checkpointing. The documentation was crystal clear and the deliverables exceeded our expectations.",
            "Exceptional attention to detail. Captured the entire history of records without skipping any nested feedback. Communication was timely, professional, and proactive. Will definitely hire again.",
            "Great experience working with this freelancer. They quickly understood our market intelligence requirements and structured the exact data model we needed for Claude analysis.",
            "Delivered ahead of schedule. The code was modular, clean, and adhered strictly to modern coding standards. 5 stars all around!",
        ]

        total_jobs_to_create = 65  # 50 on page 1, 15 on page 2 (with day > 30 cutoff on page 2)
        for i in range(total_jobs_to_create):
            tpl = titles_templates[i % len(titles_templates)]
            job_id = f"~01mock{i:04d}abcdef"
            title = f"{tpl[0]} [Batch {i+1}]"
            skills = tpl[1]
            budget_str = tpl[2]
            country = tpl[3]
            spend = tpl[4]
            rating = tpl[5]

            # Space dates:
            # First 5 jobs: Day 0 (today)
            # Jobs 5..49: Days 1 to 24 (all inside 1 month)
            # Jobs 50..55: Days 25 to 29 (inside 1 month)
            # Jobs 56..64: Days 31 to 40 (OLDER than 30-day cutoff! Must trigger stop!)
            if i < 5:
                days_ago = 0
                hours_ago = i * 2 + 1
                job_dt = self.reference_time - timedelta(hours=hours_ago)
            elif i < 50:
                days_ago = int((i - 5) * (24 / 45)) + 1
                job_dt = self.reference_time - timedelta(days=days_ago, hours=3)
            elif i < 56:
                days_ago = 25 + (i - 50)
                job_dt = self.reference_time - timedelta(days=days_ago, hours=2)
            else:
                # Past cutoff
                days_ago = 31 + (i - 56) * 2
                job_dt = self.reference_time - timedelta(days=days_ago, hours=4)

            desc = sample_descriptions[i % len(sample_descriptions)]

            # Generate 2-3 history items per job with complete reviews
            history_items = []
            for h in range(3):
                rev_text = sample_reviews[(i + h) % len(sample_reviews)]
                history_items.append(
                    {
                        "title": f"Past Milestone Assignment #{h+1}",
                        "date": f"May 2024 - Jun 2024",
                        "rating": 5.0,
                        "amount": f"${250 * (h + 1)}.00",
                        "freelancer": f"Developer_{i}_{h}",
                        "review": rev_text,
                    }
                )

            html_content = generate_mock_job_html(
                job_id=job_id,
                title=title,
                posted_dt=job_dt,
                client_country=country,
                client_spend=spend,
                client_rating=rating,
                budget_str=budget_str,
                description=desc,
                skills=skills,
                history_items=history_items,
            )

            self.jobs[job_id] = {
                "job_id": job_id,
                "job_url": f"https://www.upwork.com/jobs/{job_id}",
                "title": title,
                "posted_dt": job_dt,
                "posted_raw": f"Posted {days_ago} days ago" if days_ago > 0 else "Posted 2 hours ago",
                "html": html_content,
                "page": 1 if i < 50 else 2,
            }

    def fetch_search_page(self, page: int = 1) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Returns jobs for the requested page (50 jobs/page).
        """
        page_jobs = [j for j in self.jobs.values() if j["page"] == page]
        has_more = page < 2
        summaries = []
        for j in page_jobs:
            summaries.append(
                {
                    "job_id": j["job_id"],
                    "job_url": j["job_url"],
                    "title": j["title"],
                    "posted_raw": j["posted_raw"],
                    "posted_dt": j["posted_dt"],
                }
            )
        return summaries, has_more

    def fetch_job_details(self, job_id: str, job_url: str) -> str:
        """
        Returns full job HTML from mock fixture store.
        """
        if job_id in self.jobs:
            return self.jobs[job_id]["html"]
        raise ValueError(f"Job ID {job_id} not found in mock store")

    def close(self):
        pass
