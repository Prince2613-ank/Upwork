import re
from bs4 import BeautifulSoup

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
    # Clone or clean
    # Work on a copy or directly if acceptable
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

def extract_full_description_v2(soup: BeautifulSoup) -> str:
    primary_selectors = [
        "[data-test='job-description-text']",
        "[data-test='Description']",
        "[data-test='job-description']",
        "[data-qa='job-description']",
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
