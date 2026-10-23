"""
Parser for Upwork 'About the Client' metadata section.
"""

import re
from typing import Optional, Dict, Any
from bs4 import BeautifulSoup
from models.schema import ClientInfo


def parse_numeric_spend(spend_str: str) -> Optional[float]:
    """
    Parses strings like '$10K+', '$3.5K spent', '$500 spent', '$1.2M+' into numeric float.
    """
    if not spend_str:
        return None
    match = re.search(r"\$([\d,]+(?:\.\d+)?)\s*([KkMmBb])?", spend_str)
    if not match:
        return None
    val_str = match.group(1).replace(",", "")
    val = float(val_str)
    multiplier = match.group(2)
    if multiplier:
        m = multiplier.upper()
        if m == "K":
            val *= 1_000
        elif m == "M":
            val *= 1_000_000
        elif m == "B":
            val *= 1_000_000_000
    return val


def parse_about_client(html_or_text: str) -> ClientInfo:
    """
    Extracts structured ClientInfo from HTML or raw text of the 'About the Client' block.
    """
    if not html_or_text:
        return ClientInfo()

    if "<" in html_or_text and ">" in html_or_text:
        soup = BeautifulSoup(html_or_text, "html.parser")
        raw_text = soup.get_text(separator="\n")
    else:
        raw_text = html_or_text

    client = ClientInfo()

    # 1. Payment Verification
    if re.search(r"payment (method )?verified", raw_text, re.IGNORECASE):
        client.payment_verified = True
    elif re.search(r"payment (method )?unverified", raw_text, re.IGNORECASE):
        client.payment_verified = False

    # 2. Rating & Review Count
    # Examples: "5.0 of 12 reviews", "4.89 of 34 reviews", "5.00 5 of 5 stars"
    rating_match = re.search(r"(\d+(?:\.\d+)?)\s*(?:of\s*5|\/5)?\s*(?:stars|reviews|of\s*(\d+)\s*reviews)", raw_text, re.IGNORECASE)
    if rating_match:
        try:
            r_val = float(rating_match.group(1))
            if 0.0 <= r_val <= 5.0:
                client.rating = r_val
            if rating_match.group(2):
                client.reviews_count = int(rating_match.group(2))
        except ValueError:
            pass

    if client.reviews_count is None:
        rc_match = re.search(r"(\d+)\s+reviews?", raw_text, re.IGNORECASE)
        if rc_match:
            client.reviews_count = int(rc_match.group(1))

    # 3. Total Spend
    # Examples: "$10K+ spent", "$500 total spent", "$200+ spent"
    spend_match = re.search(r"(\$[\d,]+(?:\.\d+)?\s*[KkMmBb]?\+?\s*(?:total\s*)?spent)", raw_text, re.IGNORECASE)
    if spend_match:
        client.total_spent = spend_match.group(1).strip()
        client.total_spent_amount = parse_numeric_spend(client.total_spent)

    # 4. Jobs Posted, Hires, Hire Rate, Active
    # Examples: "24 jobs posted", "67% hire rate", "18 hires, 2 active"
    jobs_match = re.search(r"(\d+)\s+jobs?\s+posted", raw_text, re.IGNORECASE)
    if jobs_match:
        client.jobs_posted = int(jobs_match.group(1))

    hire_rate_match = re.search(r"(\d+(?:\.\d+)?)\s*%\s*hire\s*rate", raw_text, re.IGNORECASE)
    if hire_rate_match:
        client.hire_rate = float(hire_rate_match.group(1))

    hires_match = re.search(r"(\d+)\s+hires?", raw_text, re.IGNORECASE)
    if hires_match:
        client.total_hires = int(hires_match.group(1))

    active_match = re.search(r"(\d+)\s+active(?:\s+jobs?|\s+contracts?|\s+hires?)?", raw_text, re.IGNORECASE)
    if active_match:
        client.active_hires = int(active_match.group(1))

    # 5. Member Since
    # Examples: "Member since Nov 12, 2021", "Member since 2019"
    member_match = re.search(r"member\s+since\s+([A-Za-z0-9,\s]+?)(?=\n|$|\.\s)", raw_text, re.IGNORECASE)
    if member_match:
        client.member_since = member_match.group(1).strip()

    # 6. Avg Hourly Rate Paid & Hours Billed
    rate_match = re.search(r"(\$[\d,]+(?:\.\d+)?\s*\/hr\s*(?:avg\s*hourly\s*rate(?:\s*paid)?)?)", raw_text, re.IGNORECASE)
    if rate_match:
        client.avg_hourly_rate = rate_match.group(1).strip()

    hours_match = re.search(r"([\d,]+)\s+hours(?:\s+billed)?", raw_text, re.IGNORECASE)
    if hours_match:
        client.hours_billed = int(hours_match.group(1).replace(",", ""))

    # 7. Location (Country / City)
    # Examples: "Location: Netherlands", "Location: United States", "Dallas, TX 1:45 PM"
    loc_match = re.search(r"(?:location|country)\s*:\s*([^\n\r]+)", raw_text, re.IGNORECASE)
    if loc_match:
        client.location = loc_match.group(1).strip()

    if not client.location:
        lines = [l.strip() for l in raw_text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if line.lower() in ["location", "client location", "country"]:
                if i + 1 < len(lines):
                    client.location = lines[i + 1].strip()
                    break
            # Or look for country/city line before/after time string e.g. "Dallas 1:45 PM"
            time_match = re.search(r"^(.*?)\s+\d{1,2}:\d{2}\s*(?:AM|PM)", line, re.IGNORECASE)
            if time_match and not client.location:
                loc_candidate = time_match.group(1).strip()
                if loc_candidate:
                    client.location = loc_candidate

    # Guard: Clients with 0 hires and no spend have no rating
    if (not client.total_hires or client.total_hires == 0) and not client.total_spent:
        client.rating = None

    return client
