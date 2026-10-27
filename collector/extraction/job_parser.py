"""
Section 7 & 14: Job Detail Parser and Extraction Status Validator.
Extracts complete, un-truncated job descriptions preserving paragraph structure,
and compiles the CollectedJob model with explicit extraction_status flags.
"""

import re
from typing import Optional, Dict, Any, List
from bs4 import BeautifulSoup
from collector.models.schema import CollectedJob, JobDetails, ExtractionStatus
from collector.extraction.client_parser import parse_about_client
from collector.extraction.review_parser import parse_client_history
from collector.pagination.date_boundary import parse_upwork_date


def _is_metadata_snippet(txt: str) -> bool:
    t = txt.strip().lower()
    meta_keywords = [
        "fixed-price", "hourly", "experience level", "intermediate", "expert",
        "entry level", "est. budget", "payment verified", "less than 30 hrs",
        "more than 30 hrs", "hours billed", "total spent"
    ]
    if len(t) < 40 and any(m in t for m in meta_keywords):
        return True
    return False


def _clean_description_element(el) -> str:
    if not el:
        return ""
    import copy
    el_copy = copy.copy(el)
    for tag in el_copy.find_all(["button", "a", "script", "style"]):
        if re.search(r"^\s*(?:\.\.\.|\u2026)?\s*(?:more|less)\s*$", tag.get_text(), re.I):
            tag.decompose()
        elif tag.name in ["script", "style"]:
            tag.decompose()

    for br in el_copy.find_all("br"):
        br.replace_with("\n")

    lines = [p.get_text().strip() for p in el_copy.find_all(["p", "div", "li"]) if p.get_text().strip()]
    if lines:
        text = "\n\n".join(lines)
    else:
        text = el_copy.get_text(separator="\n").strip()

    text = re.sub(r"(\.\.\.|\u2026)?\s*(?:more|less)\s*$", "", text, flags=re.IGNORECASE).strip()
    return text


def extract_full_description(soup: BeautifulSoup) -> str:
    """
    Extracts complete, un-truncated job description.
    Preserves paragraph breaks and removes any UI expansion buttons ("...more", "less").
    Supports all Upwork modern, legacy, responsive, and fallback container variants.
    """
    primary_selectors = [
        "[data-test='job-description-text']",
        "[data-test='Description']",
        "[data-test='job-description']",
        "[data-qa='job-description']",
        "p.multiline-text",
        ".job-details .multiline-text",
        ".job-details .break p",
        ".job-description",
        ".description-box",
        ".up-line-clamp-expanded",
        ".job-description-text",
        "[itemprop='description']",
        ".break-word[data-v-]",
    ]

    for sel in primary_selectors:
        for el in soup.select(sel):
            txt = _clean_description_element(el)
            if len(txt) > 25 and not _is_metadata_snippet(txt):
                return txt

    container_selectors = [
        ".up-card-section .description",
        ".up-card-section article section p",
        "article section p",
        ".description",
        ".air3-card-section .description",
    ]
    for sel in container_selectors:
        for el in soup.select(sel):
            txt = _clean_description_element(el)
            if len(txt) > 35 and not _is_metadata_snippet(txt):
                return txt

    candidates = []
    for el in soup.find_all(attrs={"class": re.compile(r"description|project-requirements|job-details-text", re.I)}):
        txt = _clean_description_element(el)
        if len(txt) > 40 and not _is_metadata_snippet(txt):
            candidates.append(txt)

    if candidates:
        candidates.sort(key=len, reverse=True)
        return candidates[0]

    main_el = soup.select_one("article, main, [role='main']")
    if main_el:
        for p in main_el.select("p"):
            txt = _clean_description_element(p)
            if len(txt) > 60 and not _is_metadata_snippet(txt):
                return txt

    return ""


def extract_exact_publish_time(soup: BeautifulSoup) -> Optional[str]:
    """
    Extracts the exact ISO timestamp down to the second/millisecond from the Nuxt SSR payload.
    Bypasses UI text approximations ('Posted yesterday') and gets true publishedOn/postedOn.
    """
    nuxt = soup.find("script", id="__NUXT_DATA__")
    if nuxt and nuxt.string:
        try:
            import json
            data = json.loads(nuxt.string)
            if isinstance(data, list):
                for item in data:
                    if isinstance(item, dict) and ("publishTime" in item or "postedOn" in item):
                        for k in ["publishTime", "postedOn", "createdOn"]:
                            val_idx = item.get(k)
                            if isinstance(val_idx, int) and val_idx < len(data):
                                val = data[val_idx]
                                if isinstance(val, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val):
                                    return val
                            elif isinstance(val_idx, str) and re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", val_idx):
                                return val_idx
        except Exception:
            pass
    return None


def parse_job_detail_page(
    html: str,
    job_url: str = "",
    search_card_metadata: Optional[Dict[str, Any]] = None,
    include_history: bool = True,
) -> CollectedJob:
    """
    Parses full job detail page HTML into a validated CollectedJob model.
    Combines search card metadata with page details.
    """
    soup = BeautifulSoup(html, "html.parser")
    meta = search_card_metadata or {}

    # 1. Canonical Job URL and ID
    if not job_url:
        canon = soup.select_one("link[rel='canonical']")
        if canon and canon.get("href"):
            job_url = canon["href"].split("?")[0]
        else:
            job_url = meta.get("job_url", "https://www.upwork.com/jobs/~unknown")

    from collector.extraction.search_parser import extract_job_id_from_url
    job_id = meta.get("job_id") or extract_job_id_from_url(job_url)
    if not job_id:
        jid_el = soup.select_one("[data-job-id]")
        if jid_el and jid_el.get("data-job-id"):
            job_id = jid_el["data-job-id"]
        else:
            job_id = f"~{abs(hash(job_url)):x}"

    # 2. Job Title
    title_el = soup.select_one("h1, h4, [data-test='job-title'], .job-title")
    job_title = title_el.get_text().strip() if title_el else meta.get("job_title", "Untitled Job")
    if "job not found" in job_title.lower() or ("job not found" in soup.get_text()[:600].lower() and not title_el):
        raise ValueError(f"Job page returned 404 / Not Found for {job_url}")

    # Guard against Cloudflare rate limit / error pages
    soup_text_sample = soup.get_text()[:800].lower()
    if "error 1015" in soup_text_sample or "you are being rate limited" in soup_text_sample or ("attention required" in soup_text_sample and "cloudflare" in soup_text_sample):
        raise ValueError(f"Job page returned Cloudflare Rate Limit / Access Denied for {job_url}")

    # 3. Posted Date: Prioritize exact millisecond timestamp from Nuxt SSR payload
    posted_raw = meta.get("posted_raw") or meta.get("posted_time") or ""
    time_el = soup.select_one("[data-test='posted-on'], time, [data-test='job-pubilshed-date'], .posted-date, [class*='posted-on']")
    if time_el:
        posted_raw = time_el.get_text().strip()
    elif not posted_raw:
        for el in soup.find_all(["div", "span", "p", "small"]):
            txt = el.get_text().strip()
            if re.match(r"^Posted\s+(\d+\s+(?:minutes?|hours?|days?|weeks?|months?)\s+ago|yesterday)", txt, re.I):
                posted_raw = txt
                break

    exact_iso = extract_exact_publish_time(soup)
    if exact_iso:
        posted_at = exact_iso
        try:
            from datetime import datetime
            posted_dt = datetime.fromisoformat(exact_iso.replace("Z", "+00:00"))
        except Exception:
            posted_dt, _ = parse_upwork_date(posted_raw)
    else:
        posted_dt, posted_at = parse_upwork_date(posted_raw)

    # 4. Full Description (Section 7)
    description = extract_full_description(soup)
    if not description and meta.get("visible_job_description"):
        description = meta["visible_job_description"]
    if not description and meta.get("description_snippet"):
        description = meta["description_snippet"]

    # 5. Job Details (Budget, type, experience level, skills, proposals)
    jd = JobDetails(
        description=description,
        job_type=meta.get("job_type", ""),
        experience_level=meta.get("experience_level", ""),
        budget=meta.get("estimated_budget", ""),
        hourly_min=meta.get("hourly_min", ""),
        hourly_max=meta.get("hourly_max", ""),
        fixed_price=meta.get("fixed_price", ""),
        skills=list(meta.get("required_skills", [])),
        proposals=meta.get("proposals", ""),
    )

    # Augment skills if detail page has tags
    page_skills = soup.select("[data-test='skill'], [data-test='SkillSnippet'], .air3-token")
    for ps in page_skills:
        stxt = ps.get_text().strip()
        if stxt and stxt not in jd.skills and len(stxt) < 50:
            jd.skills.append(stxt)

    # Augment experience level if missing
    if not jd.experience_level:
        exp_el = soup.select_one("[data-test='contractor-tier'], [data-test='experience-level']")
        if exp_el:
            jd.experience_level = exp_el.get_text().strip()

    # 6. Client Section (Section 4)
    client = parse_about_client(soup)
    if not client.location and meta.get("client_location"):
        client.location = meta["client_location"]
    if meta.get("payment_verified") is True:
        client.payment_verified = True
    if not client.rating and meta.get("client_rating"):
        client.rating = meta["client_rating"]
    if not client.total_spent and meta.get("client_total_spent"):
        client.total_spent = meta["client_total_spent"]

    client_location = client.location or meta.get("client_location", "")

    # 7. Client Recent History (Section 5 & 6)
    recent_history = parse_client_history(soup) if include_history else []

    # 8. Extraction Status Validation (Section 14)
    has_full_reviews = (
        all(h.feedback_full for h in recent_history if h.feedback and h.feedback != "No feedback given")
        if recent_history else True
    )

    status = ExtractionStatus(
        job_details=bool(job_id and job_title),
        description=bool(description and len(description) > 20),
        about_client=bool(client.location or client.total_spent or client.rating or client.about_client_text),
        recent_history=True,  # attempted
        full_reviews=has_full_reviews,
    )

    return CollectedJob(
        job_id=job_id,
        job_url=job_url,
        job_title=job_title,
        posted_at=posted_at,
        posted_raw=posted_raw,
        client_location=client_location,
        job=jd,
        client=client,
        client_recent_history=recent_history,
        extraction_status=status,
    )
