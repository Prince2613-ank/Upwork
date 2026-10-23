"""
Comprehensive parser for Upwork Job Postings, combining job metadata,
full description, client information, and recent history.
"""

import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup
from models.schema import JobPosting, Budget, SourceMetadata
from .client_parser import parse_about_client
from .history_parser import parse_client_history
from .date_parser import parse_upwork_date


def parse_budget_details(text: str) -> Budget:
    """
    Extracts structured budget information from job terms text.
    Handles fixed-price ($250.00) and hourly ranges ($25.00-$50.00/hr).
    """
    b = Budget(raw_text=text.strip())
    if not text:
        return b

    cleaned = text.strip()

    # Check for Hourly: "$25.00 - $50.00 /hr" or "$30.00/hr"
    hourly_range = re.search(r"\$([\d,]+(?:\.\d+)?)\s*-\s*\$([\d,]+(?:\.\d+)?)\s*(?:\/hr|hourly)", cleaned, re.IGNORECASE)
    if hourly_range:
        b.type = "hourly"
        b.min_hourly = float(hourly_range.group(1).replace(",", ""))
        b.max_hourly = float(hourly_range.group(2).replace(",", ""))
        b.amount = (b.min_hourly + b.max_hourly) / 2.0
        return b

    single_hourly = re.search(r"\$([\d,]+(?:\.\d+)?)\s*(?:\/hr|hourly)", cleaned, re.IGNORECASE)
    if single_hourly:
        b.type = "hourly"
        amt = float(single_hourly.group(1).replace(",", ""))
        b.amount = amt
        b.min_hourly = amt
        b.max_hourly = amt
        return b

    # Check for Fixed-price: "Est. budget: $25.00", "Fixed price: $500"
    fixed_match = re.search(r"(?:budget|fixed[- ]price|est\.\s*budget)?\s*:?\s*\$([\d,]+(?:\.\d+)?)", cleaned, re.IGNORECASE)
    if fixed_match:
        b.type = "fixed-price"
        b.amount = float(fixed_match.group(1).replace(",", ""))
        return b

    if "hourly" in cleaned.lower():
        b.type = "hourly"
    elif "fixed" in cleaned.lower():
        b.type = "fixed-price"

    return b


def extract_job_id_from_url(url: str) -> str:
    """
    Extracts ciphertext job ID from Upwork job URL.
    e.g. 'https://www.upwork.com/jobs/~0123456789abcdef' -> '~0123456789abcdef'
    """
    match = re.search(r"(~[a-zA-Z0-9]+)", url)
    if match:
        return match.group(1)
    # If standard digits ID
    d_match = re.search(r"/jobs/(\d+)", url)
    if d_match:
        return d_match.group(1)
    return ""


def parse_job_posting_page(
    html_content: str,
    job_url: str = "",
    search_page: int = 1,
    source_type: str = "mock",
) -> JobPosting:
    """
    Parses a complete Upwork job posting page / drawer HTML into a validated JobPosting model.
    Ensures full description is captured without truncation and history items are populated.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Job URL and ID
    if not job_url:
        canonical_link = soup.select_one("link[rel='canonical']")
        if canonical_link and canonical_link.get("href"):
            job_url = canonical_link["href"]
        else:
            job_url = "https://www.upwork.com/jobs/~unknown"

    job_id = extract_job_id_from_url(job_url)
    if not job_id:
        # Check data attributes
        job_el = soup.select_one("[data-job-id], [data-test='job-tile'], article")
        if job_el and job_el.get("data-job-id"):
            job_id = job_el["data-job-id"]
        else:
            # Fallback deterministic hash from URL
            job_id = f"~{abs(hash(job_url)):x}"

    # 2. Job Title
    title_el = soup.select_one(
        "h1, [data-test='job-title'], .job-title, header h2"
    )
    title = title_el.get_text().strip() if title_el else "Untitled Job Posting"

    # 3. Full Job Description (MANDATORY: NO TRUNCATION)
    # Manager requirement: "Description पूरी चाहिए."
    desc_el = soup.select_one(
        "[data-test='job-description-text'], [data-test='Description'], .job-description, .up-line-clamp-expanded, [data-test='job-description']"
    )
    if not desc_el:
        desc_el = soup.select_one(".description, .air3-truncation-content, article section p")

    if desc_el:
        # Remove any lingering "more/less" toggle buttons inside the description container
        for btn in desc_el.find_all(["button", "a"], string=re.compile(r"more|less", re.I)):
            btn.decompose()
        description = desc_el.get_text(separator="\n").strip()
    else:
        description = ""

    # 4. Posted Date / Time
    posted_raw = ""
    posted_el = soup.select_one(
        "[data-test='posted-on'], time, [data-test='job-pubilshed-date'], .posted-date"
    )
    if posted_el:
        posted_raw = posted_el.get_text().strip()
        if posted_el.get("datetime"):
            posted_dt, posted_at = parse_upwork_date(posted_el["datetime"])
        else:
            posted_dt, posted_at = parse_upwork_date(posted_raw)
    else:
        # Fallback search in page text
        text_match = re.search(r"posted\s+([A-Za-z0-9,\s]+?ago|[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4})", soup.get_text(), re.IGNORECASE)
        if text_match:
            posted_raw = text_match.group(0).strip()
            posted_dt, posted_at = parse_upwork_date(posted_raw)
        else:
            posted_dt, posted_at = parse_upwork_date("just now")

    # 5. Budget / Terms
    budget_raw = ""
    terms_el = soup.select_one(
        "[data-test='job-type'], [data-test='budget'], .job-type, .up-budget"
    )
    if terms_el:
        budget_raw = terms_el.get_text().strip()
    else:
        # Try finding fixed or hourly price pattern in text
        b_match = re.search(r"(fixed[- ]price\s*-\s*[^\n]+|est\.\s*budget:\s*\$[\d,]+|\$[\d,]+(?:\.\d+)?\s*-\s*\$[\d,]+(?:\.\d+)?\s*\/hr)", soup.get_text(), re.IGNORECASE)
        if b_match:
            budget_raw = b_match.group(1).strip()
    budget = parse_budget_details(budget_raw)

    # 6. Experience Level & Duration
    exp_level = None
    exp_el = soup.select_one("[data-test='contractor-tier'], [data-test='experience-level']")
    if exp_el:
        exp_level = exp_el.get_text().strip()
    else:
        for term in ["Entry Level", "Intermediate", "Expert"]:
            if re.search(rf"\b{term}\b", soup.get_text(), re.IGNORECASE):
                exp_level = term
                break

    duration = None
    dur_el = soup.select_one("[data-test='duration']")
    if dur_el:
        duration = dur_el.get_text().strip()
    else:
        dur_match = re.search(r"(less than 1 month|1 to 3 months|3 to 6 months|more than 6 months)", soup.get_text(), re.IGNORECASE)
        if dur_match:
            duration = dur_match.group(1).strip()

    # 7. Skills
    skills: List[str] = []
    skill_elements = soup.select(
        "[data-test='skill'], [data-test='SkillSnippet'], .air3-token, .skill-badge, a[href*='search/jobs?q=']"
    )
    for sel in skill_elements:
        s_text = sel.get_text().strip()
        if s_text and s_text not in skills and len(s_text) < 50:
            skills.append(s_text)

    # 8. Category / Subcategory
    category = None
    cat_el = soup.select_one("[data-test='category'], .job-category, a[href*='freelance-jobs/']")
    if cat_el:
        category = cat_el.get_text().strip()

    # 9. Proposals / Activity
    proposals = None
    prop_el = soup.select_one("[data-test='proposals-tier'], [data-test='proposals']")
    if prop_el:
        proposals = prop_el.get_text().strip()
    else:
        prop_match = re.search(r"proposals:\s*([A-Za-z0-9\s<]+?)(?=\n|$)", soup.get_text(), re.IGNORECASE)
        if prop_match:
            proposals = prop_match.group(1).strip()

    # 10. About the Client Section
    about_client_raw = ""
    about_client_el = soup.select_one(
        "[data-test='about-client'], [data-test='client-info'], .about-client, section#about-client"
    )
    if about_client_el:
        about_client_raw = about_client_el.get_text(separator="\n").strip()
        client_info = parse_about_client(about_client_raw)
    else:
        client_info = parse_about_client(soup.get_text())

    # 11. Client's Recent History Section
    history_container = soup.select_one(
        "[data-test='client-history'], [data-test='contract-history'], .client-history, #client-history"
    )
    if history_container:
        recent_history = parse_client_history(history_container)
    else:
        recent_history = parse_client_history(soup)

    # 12. Source Metadata
    source_meta = SourceMetadata(
        source_type=source_type,
        search_page=search_page,
    )

    return JobPosting(
        job_id=job_id,
        job_url=job_url,
        title=title,
        posted_at=posted_at,
        posted_raw=posted_raw,
        description=description,
        budget=budget,
        experience_level=exp_level,
        duration=duration,
        skills=skills,
        category=category,
        proposals=proposals,
        about_client_raw=about_client_raw,
        client=client_info,
        client_recent_history=recent_history,
        source=source_meta,
    )
