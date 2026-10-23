"""
Section 4: About the Client Parser.
Strictly extracts displayed fields without inventing missing values.
"""

import re
from typing import Dict, Any, Optional
from bs4 import BeautifulSoup, Tag
from collector.models.schema import ClientSection


def parse_about_client(container_or_html: Any) -> ClientSection:
    """
    Extracts all Section 4 Client fields from the "About the Client" section.
    """
    if isinstance(container_or_html, str):
        soup = BeautifulSoup(container_or_html, "html.parser")
        client_sec = soup.select_one(
            "[data-test='about-client'], [data-test='client-info'], [data-cy='about-client'], .about-client, section#about-client"
        )
        if not client_sec:
            # Look for header containing About the client
            for sec in soup.find_all(["section", "div", "aside"]):
                h = sec.find(["h2", "h3", "h4", "strong", "span"])
                if h and "about the client" in h.get_text().lower():
                    client_sec = sec
                    break
        target = client_sec if client_sec else soup
    elif isinstance(container_or_html, Tag):
        target = container_or_html
    else:
        return ClientSection()

    raw_text = target.get_text(separator="\n").strip()
    full_text_single_line = " ".join(raw_text.split())

    c = ClientSection(about_client_text=raw_text)

    # 1. Payment Verified
    pv_el = target.select_one(
        "[data-test='payment-verified'], [aria-label*='Payment verified'], .payment-verified"
    )
    if pv_el or "payment verified" in full_text_single_line.lower() or "payment method verified" in full_text_single_line.lower():
        c.payment_verified = True
    elif "payment unverified" in full_text_single_line.lower():
        c.payment_verified = False

    # 2. Rating
    # Strip any Upwork platform footer marketing ("About Upwork", "Rating is 4.9 out of 5")
    clean_client_text = re.sub(r"about upwork.*", "", full_text_single_line, flags=re.IGNORECASE)
    m_rating = re.search(r"(\d\.\d{1,2})\s*(?:of 5|\/5|\bstars?\b)", clean_client_text, re.IGNORECASE)
    if m_rating:
        c.rating = m_rating.group(1)
    else:
        rating_el = target.select_one("[data-test='star-rating'], .rating")
        if rating_el:
            c.rating = rating_el.get_text().strip()

    # 3. Total Spent
    m_spent = re.search(r"(\$[\d,.]+[KkMmB]?\+?\s*total\s*spent|\$[\d,.]+[KkMmB]?\+?\s*spent)", clean_client_text, re.IGNORECASE)
    if m_spent:
        c.total_spent = m_spent.group(1).strip()
    else:
        spent_el = target.select_one("[data-test='total-spent']")
        if spent_el:
            c.total_spent = spent_el.get_text().strip()

    # 4. Location
    # Upwork displays city and country, or country e.g. "Netherlands", "United States", "London, United Kingdom"
    loc_el = target.select_one(
        "[data-test='client-location'], [data-test='client-country'], [data-qa='client-location']"
    )
    if loc_el:
        c.location = loc_el.get_text().strip()
    else:
        # Check text pattern like "Netherlands 4:28 PM" or "United States"
        m_loc = re.search(r"(?:location|based in)?\s*([A-Z][a-zA-Z\s,]+?)(?=\s+\d{1,2}:\d{2}\s*(?:AM|PM)|\s+Member since|$|\n)", raw_text, re.MULTILINE)
        if m_loc and len(m_loc.group(1).strip()) < 60:
            c.location = m_loc.group(1).strip()

    if c.location:
        c.location = re.sub(r"\d{1,2}:\d{2}\s*(?:AM|PM).*", "", c.location, flags=re.I).strip()
        CATEGORIES_BLACKLIST = {
            "virtual assistance", "digital marketing", "web development", "graphic design",
            "content writing", "social media marketing", "video editing", "accounting",
            "bookkeeping", "data entry", "customer service", "sales", "seo", "translation",
            "enable javascript", "just a moment", "attention required", "cloudflare", "challenge"
        }
        if c.location.lower().strip() in CATEGORIES_BLACKLIST or any(w in c.location.lower() for w in ["enable javascript", "cloudflare", "just a moment"]):
            c.location = ""

    # 5. Jobs Posted
    m_posted = re.search(r"(\d+)\s*jobs?\s*posted", full_text_single_line, re.IGNORECASE)
    if m_posted:
        c.jobs_posted = m_posted.group(1)

    # 6. Hire Rate
    m_hire_rate = re.search(r"(\d+)\s*%\s*hire\s*rate", full_text_single_line, re.IGNORECASE)
    if m_hire_rate:
        c.hire_rate = f"{m_hire_rate.group(1)}%"

    # 7. Total Hires & Active Hires
    # Format: "23 hires, 3 active" or "1 hire"
    m_hires = re.search(r"(\d+)\s*hires?", full_text_single_line, re.IGNORECASE)
    if m_hires:
        c.total_hires = m_hires.group(1)

    m_active = re.search(r"(\d+)\s*active(?:\s*hires?|\s*contracts?)?", full_text_single_line, re.IGNORECASE)
    if m_active:
        c.active_hires = m_active.group(1)

    # 8. Hours Billed (Strict: ignore "posted X hours ago" or "X hrs/week")
    cleaned_for_hours = re.sub(r"(?:posted|viewed)\s+\d+\s+hours?\s+ago", "", full_text_single_line, flags=re.IGNORECASE)
    cleaned_for_hours = re.sub(r"\d+\s*(?:hrs?|hours?)\s*\/\s*week", "", cleaned_for_hours, flags=re.IGNORECASE)
    m_hours = re.search(r"([\d,]+)\s*hours?(?:\s*billed)?", cleaned_for_hours, re.IGNORECASE)
    if m_hours:
        c.hours_billed = m_hours.group(1).replace(",", "")

    # 9. Member Since
    m_member = re.search(r"Member\s+since\s+([A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}|[A-Za-z]{3,9}\s+\d{4})", full_text_single_line, re.IGNORECASE)
    if m_member:
        c.member_since = m_member.group(1).strip()

    # 10. Client Type / Industry if displayed
    m_type = re.search(r"(?:Industry|Company type|Client type):\s*([^\n·]+)", raw_text, re.IGNORECASE)
    if m_type:
        val = m_type.group(1).strip()
        val = re.split(r"(?:Client's recent history|About the client)", val, flags=re.IGNORECASE)[0].strip()
        if len(val) < 60:
            c.client_type = val

    # Guard: Clients with 0 hires and no spend have no rating
    if (not c.total_hires or c.total_hires == "0") and not c.total_spent:
        c.rating = None

    return c
