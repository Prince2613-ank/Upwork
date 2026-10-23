"""
High-fidelity Upwork HTML Fixture Generator.
Faithfully mirrors the reference screenshot jobs and DOM structures
to guarantee testing and verification of all extraction rules.
"""

from typing import List, Dict, Any


def generate_mock_job_detail_html(
    job_id: str,
    title: str,
    location: str,
    posted_raw: str,
    budget_raw: str,
    experience: str,
    skills: List[str],
    description: str,
    client_spend: str,
    client_rating: str,
    history_count: int = 5,
) -> str:
    """Generates complete Upwork job drawer/page HTML with About Client and Recent History."""
    skills_html = "\n".join([f"<span class='air3-token' data-test='skill'>{s}</span>" for s in skills])

    history_items_html = ""
    for i in range(1, history_count + 1):
        truncated_marker = "" if i % 2 == 0 else "...more"
        feedback_body = (
            f"The freelancer did an extraordinary job on milestone #{i}. Communication was fast, "
            f"code quality exceeded our highest standards, and delivery was completed well ahead of the deadline. "
            f"We are eager to continue our long-term collaboration with this exceptional talent. Highly recommended!"
        )
        history_items_html += f"""
        <li class="air3-card-list-item history-item" data-test="history-item">
            <h4 data-test="job-title"><a href="/jobs/~past{job_id[-6:]}{i:02d}">Past Contract Milestone Assignment #{i}</a></h4>
            <div data-test="contract-date">May 2024 - Jun 2024</div>
            <div class="payment-info">Fixed-price: $250.00</div>
            <div class="rating-info"><span data-test="star-rating">5.0</span> of 5 stars</div>
            <div class="freelancer-info">Freelancer: <a href="/freelancers/~dev{i}">Engineering_Specialist_{i}</a></div>
            <div class="feedback-comment" data-test="feedback-comment">
                <p>{feedback_body} <button class="air3-btn-link" data-test="more-btn">more</button></p>
            </div>
        </li>
        """

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <title>{title} - Upwork</title>
        <link rel="canonical" href="https://www.upwork.com/jobs/{job_id}" />
    </head>
    <body>
        <main class="up-card-section" data-test="job-details">
            <h1 data-test="job-title">{title}</h1>
            <div data-test="posted-on">Posted {posted_raw}</div>
            <div data-test="contractor-tier">{experience}</div>
            <div data-test="budget">{budget_raw}</div>
            <div data-test="proposals">Proposals: Fewer than 5</div>

            <!-- Full Description (Section 7) -->
            <section class="job-description" data-test="job-description-text">
                <p>{description}</p>
                <button data-test="description-more-btn">More</button>
            </section>

            <!-- Skills -->
            <div class="skills-container">
                {skills_html}
            </div>

            <!-- About the Client (Section 4) -->
            <section id="about-client" data-test="about-client">
                <h2>About the client</h2>
                <div data-test="payment-verified">Payment method verified</div>
                <div data-test="star-rating">{client_rating} of 5 stars (18 reviews)</div>
                <div data-test="client-location">{location}</div>
                <div data-test="total-spent">{client_spend}</div>
                <div>28 jobs posted</div>
                <div>75% hire rate, 1 active hire</div>
                <div>$45.00 /hr avg hourly rate paid</div>
                <div>1,420 hours billed</div>
                <div>Member since Jan 15, 2021</div>
                <div>Company type: Enterprise Tech</div>
            </section>

            <!-- Client's Recent History (Section 5) -->
            <section id="client-history" data-test="client-history">
                <h2>Client's recent history</h2>
                <ul class="air3-card-list">
                    {history_items_html}
                </ul>
            </section>
        </main>
    </body>
    </html>
    """
    return html


MOCK_JOBS_CATALOG = [
    {
        "job_id": "~01dutch20comic001",
        "title": "Dutch -> English Comic Translation & Manual Lettering - 20 Pages",
        "location": "Netherlands",
        "posted_raw": "4 minutes ago",
        "budget_raw": "Est. budget: $25.00",
        "experience": "Entry Level",
        "skills": ["Dutch to English Translation", "Adobe Illustrator", "Lettering", "Graphic Design"],
        "description": (
            "I'm looking for someone to translate a 20-page Dutch comic into English and replace the Dutch dialogue with "
            "the English translation directly in the original comic pages. AI tools are allowed for assisting with the translation, "
            "but the final result must be carefully checked and edited to ensure high-quality English and natural phrasing.\n\n"
            "Requirements:\n"
            "- Native or fluent English speaker with excellent Dutch comprehension\n"
            "- Experience in comic lettering and graphic software (Adobe Photoshop, Illustrator, or InDesign)\n"
            "- Attention to typographical details and visual harmony of dialogue balloons\n"
            "- Final delivery must include high-resolution print-ready PDFs and editable layered source files.\n\n"
            "Please provide relevant portfolio samples of previous comic translation or lettering work with your proposal."
        ),
        "client_spend": "$3K+ spent",
        "client_rating": "5.0",
        "history_count": 8,
    },
    {
        "job_id": "~01riveanimator002",
        "title": "Rive Animator for Mobile App - Interactive UI Animations",
        "location": "United States",
        "posted_raw": "4 minutes ago",
        "budget_raw": "$40.00 - $70.00 /hr",
        "experience": "Expert",
        "skills": ["Rive", "2D Animation", "Motion Design", "Flutter", "iOS Development"],
        "description": (
            "We are seeking an expert Rive animator to create a suite of micro-interactions and interactive state machines "
            "for our upcoming mobile application built with Flutter.\n\n"
            "Scope of Work:\n"
            "- Design 12 interactive icon animations and loading transitions in Rive\n"
            "- Configure inputs, listeners, and nested artboards for state-machine-driven interactivity\n"
            "- Optimize asset sizes for seamless 60fps rendering on both iOS and Android devices\n"
            "- Coordinate directly with our frontend mobile engineering team via GitHub and Slack.\n\n"
            "Requirements:\n"
            "- Proven portfolio showcasing shipped Rive state machines in mobile applications\n"
            "- Deep understanding of vector optimization, bone rigging, and timeline trimming\n"
            "- Fast turnaround and excellent asynchronous communication."
        ),
        "client_spend": "$45K+ spent",
        "client_rating": "4.95",
        "history_count": 14,
    },
    {
        "job_id": "~01fullstackdev003",
        "title": "Full-Stack Python & React Developer for Enterprise Portal",
        "location": "United Kingdom",
        "posted_raw": "12 minutes ago",
        "budget_raw": "Fixed-price: $1,200",
        "experience": "Intermediate",
        "skills": ["Python", "FastAPI", "React", "PostgreSQL", "Tailwind CSS", "Docker"],
        "description": (
            "Our logistics consultancy is building an internal analytics portal to track global supply chain routes. "
            "We need a versatile full-stack developer to implement the core backend API endpoints and connect them to "
            "our React administrative dashboard.\n\n"
            "Key Deliverables:\n"
            "- FastAPI backend with JWT authentication and PostgreSQL ORM integration (SQLAlchemy)\n"
            "- Data processing service for ingesting CSV and JSON freight manifest files\n"
            "- Responsive React frontend dashboard with search, filter, and CSV export capabilities\n"
            "- Docker Compose configuration for local development and CI/CD deployment pipeline.\n\n"
            "Timeline: 3 weeks from project kickoff. Immediate start required."
        ),
        "client_spend": "$120K+ spent",
        "client_rating": "5.0",
        "history_count": 22,
    },
]


def generate_mock_search_page_html() -> str:
    """Generates search results page HTML containing the 3 catalog jobs."""
    tiles = ""
    for j in MOCK_JOBS_CATALOG:
        skills_spans = " ".join([f"<span class='air3-token' data-test='skill'>{s}</span>" for s in j["skills"]])
        tiles += f"""
        <article class="job-tile" data-test="JobTile" data-job-id="{j['job_id']}">
            <h2 class="job-title"><a href="/jobs/{j['job_id']}" data-test="job-tile-title-link">{j['title']}</a></h2>
            <div data-test="posted-on">Posted {j['posted_raw']}</div>
            <div data-test="payment-verified">Payment verified</div>
            <span data-test="star-rating">{j['client_rating']}</span>
            <span data-test="total-spent">{j['client_spend']}</span>
            <span data-test="client-country">{j['location']}</span>
            <div class="job-type-budget">{j['budget_raw']}</div>
            <p data-test="job-description-text">{j['description'][:180]} ...more</p>
            <div class="skills">{skills_spans}</div>
            <span data-test="proposals">Proposals: Fewer than 5</span>
        </article>
        """

    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Search Freelance Jobs on Upwork</title></head>
    <body>
        <div data-test="job-tile-list">
            {tiles}
        </div>
        <button data-test="next-page" disabled>Next</button>
    </body>
    </html>
    """
