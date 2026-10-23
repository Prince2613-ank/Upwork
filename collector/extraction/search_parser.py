"""
Search Results Card Parser for Upwork.
Extracts all 18+ required metadata fields from search result cards (Section 2).
"""

import re
from typing import Dict, Any, List, Optional
from bs4 import BeautifulSoup, Tag
from collector.pagination.date_boundary import parse_upwork_date


def extract_job_id_from_url(url: str) -> str:
    """Extracts job ciphertext or numeric ID from URL e.g. ~01abcdef..."""
    m = re.search(r"(~[a-zA-Z0-9]+)", url)
    if m:
        return m.group(1)
    m2 = re.search(r"/jobs/(\d+)", url)
    if m2:
        return m2.group(1)
    return ""


def parse_search_card(card: Tag) -> Dict[str, Any]:
    """
    Extracts all metadata displayed on a single Upwork search result card.
    Adheres strictly to Section 2 specification.
    """
    # 1. Job Link & Title
    link = card.select_one("a[href*='/jobs/'], [data-test='job-tile-title-link'], h2 a, h3 a")
    job_url = ""
    job_title = ""
    if link:
        href = link.get("href", "")
        if href.startswith("/"):
            job_url = f"https://www.upwork.com{href}"
        else:
            job_url = href
        # Strip query parameters from job URL for canonical form
        job_url = job_url.split("?")[0]
        job_title = link.get_text().strip()

    job_id = extract_job_id_from_url(job_url)
    if not job_id:
        jid_attr = card.get("data-job-id") or card.get("data-ev-job-uid")
        if jid_attr:
            job_id = str(jid_attr)

    if not job_url and job_id:
        if str(job_id).isdigit():
            safe_jid = f"~02{job_id}"
        else:
            safe_jid = job_id if str(job_id).startswith("~") else f"~{job_id}"
        job_url = f"https://www.upwork.com/jobs/{safe_jid}"

    # 2. Posted Time & Normalized Datetime
    time_el = card.select_one(
        "[data-test='posted-on'], time, .posted-date, [data-test='job-pubilshed-date']"
    )
    posted_raw = ""
    if time_el:
        span_child = time_el.select_one("span")
        if span_child:
            posted_raw = span_child.get_text().strip()
        else:
            posted_raw = time_el.get_text().strip()
    else:
        # Check text search
        m_posted = re.search(r"posted\s+([^·\n]+)", card.get_text(), re.IGNORECASE)
        if m_posted:
            posted_raw = m_posted.group(0).strip()

    if posted_raw:
        posted_raw = re.split(r"[\u00b7\ufffd\xb7\n]|Proposals:", posted_raw, flags=re.I)[0].strip()

    posted_dt, normalized_posted = parse_upwork_date(posted_raw)

    # 3. Client Attributes on Card
    payment_verified = False
    pv_el = card.select_one(
        "[data-test='payment-verified'], [data-qa='payment-verified'], .payment-verified, [aria-label*='Payment verified']"
    )
    if pv_el or "payment verified" in card.get_text().lower():
        payment_verified = True

    # Client Rating
    client_rating = ""
    rating_el = card.select_one(
        "[data-test='star-rating'], [data-qa='client-rating'], .rating, span[class*='rating']"
    )
    if rating_el:
        client_rating = rating_el.get_text().strip()
    else:
        m_rat = re.search(r"(\d(?:\.\d)?)\s*(?:of\s*5\s*stars|\/5|\s*stars)", card.get_text(), re.IGNORECASE)
        if m_rat:
            client_rating = m_rat.group(1)

    # Client Total Spent
    client_total_spent = ""
    spent_el = card.select_one(
        "[data-test='total-spent'], [data-qa='client-spend'], [class*='spend']"
    )
    if spent_el:
        client_total_spent = spent_el.get_text().strip()
    else:
        m_spent = re.search(r"(\$[\d,.]+[KkMmB]?\+?\s*spent)", card.get_text(), re.IGNORECASE)
        if m_spent:
            client_total_spent = m_spent.group(1)

    # Client Location
    client_location = ""
    loc_el = card.select_one(
        "[data-test='location'], [data-test='client-country'], [data-qa='client-location'], [class*='client-location']"
    )
    if loc_el:
        client_location = loc_el.get_text().strip()
        client_location = re.sub(r"^location\s*", "", client_location, flags=re.I).strip()
    else:
        # Look for location icon sibling
        loc_icon = card.select_one("[data-test='location-pin'], svg[data-name='Location']")
        if loc_icon and loc_icon.parent:
            client_location = loc_icon.parent.get_text().strip()
            client_location = re.sub(r"^location\s*", "", client_location, flags=re.I).strip()

    # 4. Budget, Hourly Min/Max, Fixed Price, Job Type, Experience Level
    card_text = card.get_text(separator=" ")
    job_type = ""
    hourly_min = ""
    hourly_max = ""
    fixed_price = ""
    estimated_budget = ""

    # Hourly match e.g. "$25.00 - $50.00 /hr"
    m_hourly_range = re.search(r"\$([\d,]+(?:\.\d+)?)\s*-\s*\$([\d,]+(?:\.\d+)?)\s*(?:\/hr|hourly)", card_text, re.IGNORECASE)
    if m_hourly_range:
        job_type = "Hourly"
        hourly_min = m_hourly_range.group(1).replace(",", "")
        hourly_max = m_hourly_range.group(2).replace(",", "")
        estimated_budget = f"${hourly_min} - ${hourly_max}/hr"
    else:
        m_hourly_single = re.search(r"\$([\d,]+(?:\.\d+)?)\s*(?:\/hr|hourly)", card_text, re.IGNORECASE)
        if m_hourly_single:
            job_type = "Hourly"
            hourly_min = m_hourly_single.group(1).replace(",", "")
            hourly_max = hourly_min
            estimated_budget = f"${hourly_min}/hr"

    # Fixed price match e.g. "Est. budget: $25.00" or "Fixed-price: $500"
    m_fixed = re.search(r"(?:budget|fixed[- ]price|est\.\s*budget)?\s*:?\s*\$([\d,]+(?:\.\d+)?)", card_text, re.IGNORECASE)
    if "fixed" in card_text.lower():
        job_type = "Fixed-price"
        if m_fixed:
            fixed_price = m_fixed.group(1).replace(",", "")
            if not estimated_budget:
                estimated_budget = f"${fixed_price}"

    # Experience Level
    experience_level = ""
    for level in ["Entry Level", "Intermediate", "Expert"]:
        if re.search(rf"\b{level}\b", card_text, re.IGNORECASE):
            experience_level = level
            break

    # Proposals
    proposals = ""
    m_prop = re.search(r"proposals:\s*([^\n·]+)", card_text, re.IGNORECASE)
    if m_prop:
        proposals = m_prop.group(1).strip()
    elif "fewer than 5" in card_text.lower():
        proposals = "Fewer than 5"

    # Required Skills
    required_skills: List[str] = []
    skill_elements = card.select(
        "[data-test='skill'], [data-test='SkillSnippet'], .air3-token, .skill-badge"
    )
    for sel in skill_elements:
        s_txt = sel.get_text().strip()
        if s_txt and s_txt not in required_skills and len(s_txt) < 50:
            required_skills.append(s_txt)

    # Visible Job Description (Card preview)
    desc_el = card.select_one(
        "[data-test='job-description-text'], [data-test='Description'], .job-description, p"
    )
    visible_job_description = desc_el.get_text().strip() if desc_el else ""

    return {
        "job_id": job_id,
        "job_url": job_url,
        "job_title": job_title,
        "posted_time": posted_raw,
        "normalized_posted_datetime": normalized_posted,
        "client_location": client_location,
        "payment_verified": payment_verified,
        "client_rating": client_rating,
        "client_total_spent": client_total_spent,
        "estimated_budget": estimated_budget,
        "hourly_min": hourly_min,
        "hourly_max": hourly_max,
        "fixed_price": fixed_price,
        "experience_level": experience_level,
        "job_type": job_type,
        "proposals": proposals,
        "required_skills": required_skills,
        "visible_job_description": visible_job_description,
    }


def parse_search_page_html(html: str) -> List[Dict[str, Any]]:
    """Extracts all job cards found on an Upwork search results page."""
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select(
        "article[data-test='JobTile'], [data-test='JobTile'], .job-tile, article.up-card-section, article"
    )

    results = []
    for card in cards:
        parsed = parse_search_card(card)
        if parsed.get("job_url") and parsed.get("job_url").startswith("http"):
            results.append(parsed)

    return results
