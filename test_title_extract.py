import os
import re
import json
import sqlite3
from bs4 import BeautifulSoup
import sys
sys.stdout.reconfigure(encoding='utf-8')

def extract_true_title_and_details(jid, job_data, html_content, log_url=None):
    """
    Extracts 100% authentic, un-truncated title and details from raw HTML or fallback sources.
    """
    soup = BeautifulSoup(html_content, 'html.parser') if html_content else None
    
    # 1. Title Extraction
    true_title = ""
    if soup:
        # Check <title> tag
        title_tag = soup.find('title')
        if title_tag:
            t_txt = title_tag.get_text().strip()
            # Remove Upwork boilerplate suffixes
            # e.g., "impact.com Affiliate & Creator Manager – Mobile App Paid Subscriber Growth - Marketing, PR & Brand Strategy"
            # or "... - Upwork"
            t_clean = re.sub(r'\s*\|\s*Upwork.*$', '', t_txt, flags=re.I)
            # Remove category suffix if separated by " - "
            parts = re.split(r'\s+-\s+(?:Marketing|Design|Development|Writing|Admin|Customer|Sales|Accounting|Legal|Engineering|IT|Web|Mobile|Software|Data|AI|Translation)', t_clean, flags=re.I)
            if parts and len(parts[0].strip()) > 5:
                cand = parts[0].strip()
                if not any(bad in cand.lower() for bad in ["just a moment", "access denied", "featured job posts", "search freelance jobs", "page not found"]):
                    true_title = cand
        
        # Check <h4> or <h1> headers in detail container
        if not true_title:
            for sel in ["header h1", "header h4", "[data-test='job-title']", "h4.job-title", "h1.job-title", "main h4", "main h1"]:
                el = soup.select_one(sel)
                if el:
                    txt = el.get_text(strip=True)
                    if len(txt) > 5 and not any(bad in txt.lower() for bad in ["featured job posts", "search freelance jobs", "upwork"]):
                        true_title = txt
                        break

    # If title still not found or suspicious, check URL slug
    url = job_data.get('job_url') or log_url or ""
    if not true_title or len(true_title) <= 5:
        m_slug = re.search(r'/jobs/([^_/?#]+)_~', url)
        if m_slug:
            slug = m_slug.group(1).replace('-', ' ').replace('_', ' ').strip()
            if len(slug) > 5:
                true_title = slug

    if not true_title:
        true_title = (job_data.get('job_title') or job_data.get('title') or "Untitled Job").strip()

    return true_title

# Test on ~022089338363935389527
target_jid = '~022089338363935389527'
safe_target = target_jid.replace('~', '')
html_path = f"output/raw_html/{safe_target}.html"

with open(html_path, 'r', encoding='utf-8', errors='ignore') as f:
    raw = f.read()

conn = sqlite3.connect('output/database_14days.db')
c = conn.cursor()
r = c.execute('SELECT job_json FROM jobs WHERE job_id = ?', (target_jid,)).fetchone()
conn.close()

data = json.loads(r[0])
extracted_title = extract_true_title_and_details(target_jid, data, raw)
print("Target Job ID:", target_jid)
print("Old DB Title:", repr(data.get('job_title')))
print("Extracted Authentic Title:", repr(extracted_title))
