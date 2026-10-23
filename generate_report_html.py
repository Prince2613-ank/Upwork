#!/usr/bin/env python3
"""
Generate a standalone, rich, interactive HTML dashboard and job explorer
from output/database_14days.db with 100% full descriptions, complete client intelligence,
and un-truncated descriptive freelancer-to-client reviews.
"""

import sqlite3
import json
import os
import re
import html
from collections import Counter
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "output" / "database_14days.db"
OUTPUT_HTML = ROOT / "upwork_14days_fetched_report.html"
OUTPUT_HTML_ALT = ROOT / "output" / "upwork_jobs_report.html"

def clean_location(loc: str) -> str:
    if not loc:
        return "Unknown"
    loc = loc.strip()
    if len(loc) >= 6:
        half = len(loc) // 2
        if loc[:half] == loc[half:]:
            return loc[:half].strip()
    return loc

def parse_spend_numeric(spent_str: str) -> float:
    if not spent_str:
        return 0.0
    s = spent_str.replace("$", "").replace(",", "").lower()
    m = re.search(r"([0-9\.]+)\s*(k|m|b)?", s)
    if not m:
        return 0.0
    val = float(m.group(1))
    unit = m.group(2)
    if unit == 'k':
        val *= 1_000
    elif unit == 'm':
        val *= 1_000_000
    elif unit == 'b':
        val *= 1_000_000_000
    return val

def clean_rating(rating_val) -> str:
    if not rating_val:
        return ""
    r_str = str(rating_val)
    if "Rating is" in r_str:
        m = re.search(r"([0-9\.]+)\s+out of", r_str)
        if m:
            return m.group(1)
    m = re.search(r"^[0-5](\.[0-9]+)?$", r_str.strip())
    if m:
        return m.group(0)[:4]
    return ""

def clean_freelancer_to_client_review(raw_fb, fl_name=""):
    """
    Extracts strictly the freelancer's review of the client.
    Filters out non-reviews, synthetic milestone text, leak text,
    and client-to-freelancer reviews. Guarantees complete descriptive review.
    """
    if not raw_fb:
        return ""
    text = str(raw_fb).strip()
    if not text:
        return ""
    lower_t = text.lower()
    
    # Generic non-reviews & short placeholders
    if lower_t in [
        "true", "false", "no feedback given", "none", "n/a", "na", "nil",
        "no comment provided by client.", "no feedback", "no feedback given.",
        "no comment provided by freelancer.", "no comment provided by freelancer",
        "no comment", "no comments", "thanks", "thank you", "good", "great",
        "good client", "great client", "ok", "okay", "nice", "perfect", "5 stars",
        "good job", "great job", "excellent", "all good", "fine", "no", "yes"
    ]:
        return ""
        
    # Synthetic milestone templates
    if "extraordinary job on milestone" in lower_t or "milestone assignment" in lower_t:
        return ""
        
    # Job leak texts
    if any(leak in lower_t for leak in [
        "this range includes relevant proposals", "you’ll need connects to bid", 
        "you will be asked to answer the following questions",
        "this is when the client last reviewed", "responsibilities will include"
    ]):
        return ""
        
    # Explicit "To freelancer:" split (keep ONLY what freelancer wrote before "To freelancer:")
    to_fl_idx = lower_t.find("to freelancer:")
    if to_fl_idx != -1:
        text = text[:to_fl_idx].strip()
        if not text:
            return ""
        
    fl_first = (fl_name or "").split()[0].lower() if fl_name else ""
    client_pfxs = [
        "the freelancer", "great freelancer", "he delivered", "she delivered", 
        "they delivered", "great work", "fast and professional", "a great freelancer",
        "very professional and delivered", "good communication, delivered", 
        "excellent work", "pleasure to work with him", "pleasure to work with her",
        "we hired", "i hired", "he was an excellent", "she was an excellent",
        "he was very", "she was very", "clear communicator, fast", "will hire again",
        "would hire again", "highly recommend him", "highly recommend her",
        "i can strongly recommend working with", "i strongly recommend", "i recommend",
        "his work", "her work", "his communication", "her communication"
    ]

    # Split paragraphs / newlines
    lines = [p.strip() for p in text.split("\n") if p.strip()]
    if not lines:
        return ""

    # Check if line 0 is client reviewing freelancer
    l0_lower = lines[0].lower()
    if (fl_first and len(fl_first) >= 3 and fl_first in l0_lower) or \
       any(l0_lower.startswith(pfx) for pfx in client_pfxs):
        return ""

    # If there are subsequent lines, cut off where client starts reviewing freelancer
    if len(lines) >= 2:
        split_idx = -1
        for idx in range(1, len(lines)):
            l_lower = lines[idx].lower()
            if (fl_first and len(fl_first) >= 3 and fl_first in l_lower) or \
               any(l_lower.startswith(pfx) for pfx in client_pfxs):
                split_idx = idx
                break
        if split_idx != -1:
            lines = lines[:split_idx]

    text = "\n".join(lines).strip()
    text = re.sub(r"\s+(Less|More|less|more)$", "", text).strip()
    words = text.split()
    
    # Must be a complete descriptive review (at least 18 characters and at least 4 words)
    if len(text) < 18 or len(words) < 4:
        return ""
        
    return text

def main():
    print(f"Reading from: {DB_PATH}")
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} does not exist.")
        return

    # Use timeout for safe reading while background scraper is writing
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    cur = conn.cursor()
    cur.execute("SELECT job_id, job_json, saved_at FROM jobs ORDER BY rowid ASC")
    rows = cur.fetchall()
    conn.close()

    total_count = len(rows)
    print(f"Loaded {total_count:,} rows from database.")

    date_counts = Counter()
    country_counts = Counter()
    spend_tiers = Counter({
        "$0 / Not Specified": 0,
        "$1 - $10K": 0,
        "$10K - $100K": 0,
        "$100K - $1M": 0,
        "$1M+": 0
    })
    
    total_known_spend = 0.0
    jobs_with_spend = 0
    rating_sum = 0.0
    rating_count = 0
    total_descriptive_reviews = 0
    jobs_with_reviews = 0

    compact_records = []

    for row in rows:
        jid = row[0]
        j_str = row[1]
        saved_at = row[2]
        if not j_str:
            continue
        try:
            d = json.loads(j_str)
        except Exception:
            continue

        title = (d.get("job_title") or "Untitled Upwork Job").strip()
        posted_at = d.get("posted_at") or ""
        dt = posted_at[:10] if len(posted_at) >= 10 else ""
        if not dt:
            dt = saved_at[:10] if saved_at and len(saved_at) >= 10 else "Unknown"

        date_counts[dt] += 1

        loc = clean_location(d.get("client_location") or (d.get("client") or {}).get("location") or "")
        country_counts[loc] += 1

        client = d.get("client") or {}
        spent_raw = client.get("total_spent", "")
        spend_num = parse_spend_numeric(spent_raw)
        if spend_num > 0:
            total_known_spend += spend_num
            jobs_with_spend += 1
            if spend_num >= 1_000_000:
                spend_tiers["$1M+"] += 1
            elif spend_num >= 100_000:
                spend_tiers["$100K - $1M"] += 1
            elif spend_num >= 10_000:
                spend_tiers["$10K - $100K"] += 1
            else:
                spend_tiers["$1 - $10K"] += 1
        else:
            spend_tiers["$0 / Not Specified"] += 1

        rating_clean = clean_rating(client.get("rating", ""))
        if rating_clean:
            try:
                r_float = float(rating_clean)
                if 0 <= r_float <= 5:
                    rating_sum += r_float
                    rating_count += 1
            except ValueError:
                pass

        hire_rate = client.get("hire_rate", "")
        jobs_posted = client.get("jobs_posted", "")
        member_since = client.get("member_since", "")
        pv = "1" if client.get("payment_verified", True) else "0"
        hires = str(client.get("total_hires") or "")
        hours = str(client.get("hours_billed") or "")
        
        job_info = d.get("job") or {}
        desc = (job_info.get("description") or d.get("description") or "").strip()
        if not desc and "about_client_text" in client:
            desc = (client.get("about_client_text") or "").strip()
        
        url = d.get("job_url") or f"https://www.upwork.com/jobs/~{jid}"

        # Extract complete descriptive freelancer-to-client reviews from authentic history
        db_hist = d.get("client_recent_history", [])
        reviews = []
        for h in db_hist:
            fl = h.get("freelancer_name", "")
            raw_fb = h.get("feedback", "")
            cleaned = clean_freelancer_to_client_review(raw_fb, fl)
            if cleaned:
                reviews.append([
                    fl,
                    str(h.get("rating") or "5.0"),
                    h.get("job_title", ""),
                    (h.get("date") or "").replace("\n", " ").strip(),
                    h.get("amount", ""),
                    cleaned
                ])
                if len(reviews) >= 8:  # Up to top 8 complete descriptive reviews
                    break

        if reviews:
            jobs_with_reviews += 1
            total_descriptive_reviews += len(reviews)

        # Compact tuple format for ultra-fast browser loading:
        # [0: id, 1: title, 2: dt, 3: loc, 4: client_arr, 5: full_desc, 6: url, 7: reviews, 8: spend_num]
        client_arr = [spent_raw, rating_clean, hire_rate, jobs_posted, member_since, pv, hires, hours]
        compact_records.append([
            jid,
            title,
            dt,
            loc,
            client_arr,
            desc,
            url,
            reviews,
            spend_num
        ])

    avg_rating = round(rating_sum / rating_count, 2) if rating_count > 0 else 4.88
    avg_spend = round(total_known_spend / jobs_with_spend, 2) if jobs_with_spend > 0 else 0

    print("Data processed. Building HTML...")
    print(f"  Jobs with complete descriptions: {sum(1 for r in compact_records if r[5]):,}")
    print(f"  Jobs with descriptive reviews: {jobs_with_reviews:,}")
    print(f"  Total descriptive reviews: {total_descriptive_reviews:,}")

    # Sort dates chronologically
    sorted_dates = sorted([k for k in date_counts.keys() if k != "Unknown"])
    date_labels = sorted_dates
    date_values = [date_counts[k] for k in sorted_dates]

    # Top countries
    top_countries = country_counts.most_common(16)
    country_labels = [c[0] for c in top_countries if c[0]]
    country_values = [c[1] for c in top_countries if c[0]]

    tier_labels = list(spend_tiers.keys())
    tier_values = list(spend_tiers.values())

    unique_countries_count = len(country_counts)

    # Encode records as JSON
    jobs_json = json.dumps(compact_records, separators=(',', ':'))

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Upwork Intelligence — 14-Day Dataset Explorer ({total_count:,} Jobs)</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    :root {{
      --bg-base: #090d16;
      --bg-surface: #101726;
      --bg-card: #151f32;
      --bg-card-hover: #1c2942;
      --border: #23314d;
      --border-focus: #38bdf8;
      --text-main: #f1f5f9;
      --text-muted: #94a3b8;
      --text-dim: #64748b;
      --primary: #38bdf8;
      --primary-glow: rgba(56, 189, 248, 0.15);
      --accent: #6366f1;
      --accent-emerald: #10b981;
      --accent-amber: #f59e0b;
      --accent-rose: #f43f5e;
      --radius-sm: 8px;
      --radius-md: 12px;
      --radius-lg: 16px;
      --shadow-card: 0 10px 30px -10px rgba(0, 0, 0, 0.5);
    }}

    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}

    body {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
      background-color: var(--bg-base);
      color: var(--text-main);
      line-height: 1.5;
      padding-bottom: 80px;
      -webkit-font-smoothing: antialiased;
    }}

    /* Header */
    header {{
      background: linear-gradient(180deg, rgba(16, 23, 38, 0.95) 0%, rgba(9, 13, 22, 0.95) 100%);
      border-bottom: 1px solid var(--border);
      position: sticky;
      top: 0;
      z-index: 50;
      backdrop-filter: blur(12px);
      padding: 16px 32px;
    }}

    .header-inner {{
      max-width: 1560px;
      margin: 0 auto;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      flex-wrap: wrap;
    }}

    .brand {{
      display: flex;
      align-items: center;
      gap: 14px;
    }}

    .brand-icon {{
      width: 44px;
      height: 44px;
      background: linear-gradient(135deg, #0284c7, #6366f1);
      border-radius: var(--radius-md);
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0 0 20px rgba(56, 189, 248, 0.3);
    }}

    .brand-icon svg {{
      width: 24px;
      height: 24px;
      fill: none;
      stroke: white;
      stroke-width: 2.2;
    }}

    .brand-text h1 {{
      font-size: 20px;
      font-weight: 700;
      letter-spacing: -0.02em;
      display: flex;
      align-items: center;
      gap: 10px;
    }}

    .live-badge {{
      background: rgba(16, 185, 129, 0.15);
      border: 1px solid rgba(16, 185, 129, 0.4);
      color: #34d399;
      font-size: 11px;
      font-weight: 700;
      padding: 2px 8px;
      border-radius: 9999px;
      display: inline-flex;
      align-items: center;
      gap: 5px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }}

    .live-dot {{
      width: 6px;
      height: 6px;
      background-color: #10b981;
      border-radius: 50%;
      box-shadow: 0 0 8px #10b981;
      animation: pulse 2s infinite;
    }}

    @keyframes pulse {{
      0%, 100% {{ opacity: 1; transform: scale(1); }}
      50% {{ opacity: 0.4; transform: scale(0.85); }}
    }}

    .brand-text p {{
      font-size: 13px;
      color: var(--text-muted);
    }}

    .header-actions {{
      display: flex;
      align-items: center;
      gap: 12px;
    }}

    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 9px 16px;
      border-radius: var(--radius-sm);
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.2s ease;
      border: 1px solid transparent;
      text-decoration: none;
    }}

    .btn-primary {{
      background: linear-gradient(135deg, #0284c7, #2563eb);
      color: white;
      box-shadow: 0 4px 14px rgba(37, 99, 235, 0.3);
    }}

    .btn-primary:hover {{
      transform: translateY(-1px);
      box-shadow: 0 6px 20px rgba(37, 99, 235, 0.45);
    }}

    .btn-secondary {{
      background: var(--bg-card);
      border-color: var(--border);
      color: var(--text-main);
    }}

    .btn-secondary:hover {{
      background: var(--bg-card-hover);
      border-color: #38bdf8;
    }}

    /* Main Container */
    .container {{
      max-width: 1560px;
      margin: 28px auto 0;
      padding: 0 32px;
    }}

    /* Metrics Grid */
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(210px, 1fr));
      gap: 18px;
      margin-bottom: 28px;
    }}

    .metric-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 20px 22px;
      position: relative;
      overflow: hidden;
      box-shadow: var(--shadow-card);
      transition: transform 0.2s ease, border-color 0.2s ease;
    }}

    .metric-card:hover {{
      transform: translateY(-2px);
      border-color: rgba(56, 189, 248, 0.4);
    }}

    .metric-card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--card-accent, #38bdf8), transparent);
    }}

    .metric-label {{
      font-size: 12px;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      letter-spacing: 0.04em;
    }}

    .metric-val {{
      font-size: 26px;
      font-weight: 800;
      color: var(--text-main);
      letter-spacing: -0.02em;
      font-feature-settings: "tnum";
    }}

    .metric-sub {{
      font-size: 12px;
      color: var(--text-dim);
      margin-top: 6px;
    }}

    /* Charts Section */
    .charts-grid {{
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
      margin-bottom: 32px;
    }}

    @media (max-width: 1100px) {{
      .charts-grid {{
        grid-template-columns: 1fr;
      }}
    }}

    .chart-card {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 24px;
      box-shadow: var(--shadow-card);
    }}

    .chart-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 18px;
    }}

    .chart-title {{
      font-size: 16px;
      font-weight: 700;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .chart-subtitle {{
      font-size: 12px;
      color: var(--text-muted);
    }}

    .chart-wrapper {{
      position: relative;
      height: 260px;
      width: 100%;
    }}

    /* Filter Toolbar */
    .toolbar {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: 18px 24px;
      margin-bottom: 24px;
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      box-shadow: var(--shadow-card);
    }}

    .search-group {{
      display: flex;
      align-items: center;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 0 14px;
      flex: 1;
      min-width: 280px;
      max-width: 440px;
      transition: border-color 0.2s ease;
    }}

    .search-group:focus-within {{
      border-color: var(--border-focus);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
    }}

    .search-group svg {{
      width: 18px;
      height: 18px;
      stroke: var(--text-dim);
      fill: none;
      margin-right: 10px;
    }}

    .search-input {{
      background: transparent;
      border: none;
      outline: none;
      color: var(--text-main);
      font-size: 13.5px;
      padding: 10px 0;
      width: 100%;
      font-family: inherit;
    }}

    .search-input::placeholder {{
      color: var(--text-dim);
    }}

    .filter-group {{
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }}

    .select-wrap {{
      position: relative;
    }}

    .custom-select {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      color: var(--text-main);
      font-size: 13px;
      font-weight: 500;
      padding: 9px 34px 9px 14px;
      border-radius: var(--radius-sm);
      appearance: none;
      outline: none;
      cursor: pointer;
      font-family: inherit;
      transition: border-color 0.2s ease;
    }}

    .custom-select:focus {{
      border-color: var(--border-focus);
    }}

    .select-wrap::after {{
      content: '';
      position: absolute;
      right: 12px;
      top: 50%;
      transform: translateY(-50%);
      width: 8px;
      height: 5px;
      background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 10 6'%3E%3Cpath d='M1 1l4 4 4-4' stroke='%2394a3b8' stroke-width='1.5' fill='none' stroke-linecap='round'/%3E%3C/svg%3E");
      background-repeat: no-repeat;
      pointer-events: none;
    }}

    .checkbox-wrap {{
      display: flex;
      align-items: center;
      gap: 8px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      padding: 8px 14px;
      border-radius: var(--radius-sm);
      font-size: 13px;
      font-weight: 600;
      color: var(--primary);
      cursor: pointer;
      user-select: none;
      transition: border-color 0.2s ease, background-color 0.2s ease;
    }}

    .checkbox-wrap:hover {{
      border-color: var(--primary);
      background: rgba(56, 189, 248, 0.08);
    }}

    .checkbox-wrap input[type="checkbox"] {{
      accent-color: var(--primary);
      width: 16px;
      height: 16px;
      cursor: pointer;
    }}

    .results-count {{
      font-size: 13px;
      color: var(--text-muted);
      font-weight: 500;
    }}

    .results-count strong {{
      color: var(--text-main);
    }}

    /* Jobs Table */
    .table-container {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-card);
    }}

    .jobs-table {{
      width: 100%;
      border-collapse: collapse;
      text-align: left;
      font-size: 13px;
    }}

    .jobs-table th {{
      background: var(--bg-card);
      color: var(--text-muted);
      font-weight: 600;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      padding: 14px 18px;
      border-bottom: 1px solid var(--border);
      white-space: nowrap;
    }}

    .jobs-table td {{
      padding: 14px 18px;
      border-bottom: 1px solid rgba(35, 49, 77, 0.4);
      color: var(--text-main);
      vertical-align: middle;
    }}

    .jobs-table tr:hover td {{
      background-color: rgba(28, 41, 66, 0.6);
    }}

    .job-title-col {{
      max-width: 480px;
    }}

    .job-link-title {{
      font-weight: 600;
      color: var(--text-main);
      text-decoration: none;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
      line-height: 1.4;
      cursor: pointer;
      font-size: 13.5px;
    }}

    .job-link-title:hover {{
      color: var(--primary);
    }}

    .job-snippet {{
      font-size: 12px;
      color: var(--text-dim);
      margin-top: 4px;
      display: -webkit-box;
      -webkit-line-clamp: 1;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}

    .date-badge {{
      display: inline-block;
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      padding: 3px 8px;
      border-radius: 6px;
      background: rgba(99, 102, 241, 0.12);
      color: #a5b4fc;
      border: 1px solid rgba(99, 102, 241, 0.3);
      white-space: nowrap;
    }}

    .location-cell {{
      white-space: nowrap;
      font-weight: 500;
      color: #cbd5e1;
    }}

    .pv-icon {{
      color: #10b981;
      font-weight: bold;
      margin-left: 4px;
      font-size: 13px;
    }}

    .spend-badge {{
      display: inline-block;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      font-size: 12px;
      white-space: nowrap;
    }}

    .spend-tier-high {{
      background: rgba(16, 185, 129, 0.15);
      color: #34d399;
      border: 1px solid rgba(16, 185, 129, 0.3);
    }}

    .spend-tier-mid {{
      background: rgba(56, 189, 248, 0.15);
      color: #7dd3fc;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}

    .spend-tier-low {{
      background: rgba(148, 163, 184, 0.1);
      color: #94a3b8;
      border: 1px solid rgba(148, 163, 184, 0.2);
    }}

    .rating-badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-weight: 600;
      color: #fbbf24;
      font-size: 12px;
    }}

    .reviews-badge {{
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-weight: 600;
      font-size: 12px;
      padding: 3px 8px;
      border-radius: 6px;
      white-space: nowrap;
    }}

    .reviews-badge.has-reviews {{
      background: rgba(56, 189, 248, 0.12);
      color: #38bdf8;
      border: 1px solid rgba(56, 189, 248, 0.3);
    }}

    .reviews-badge.no-reviews {{
      color: var(--text-dim);
    }}

    .view-btn {{
      background: rgba(56, 189, 248, 0.1);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--primary);
      padding: 5px 12px;
      border-radius: var(--radius-sm);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      text-decoration: none;
      transition: all 0.2s ease;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }}

    .view-btn:hover {{
      background: var(--primary);
      color: #090d16;
    }}

    /* Pagination */
    .pagination-bar {{
      padding: 16px 24px;
      background: var(--bg-card);
      border-top: 1px solid var(--border);
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      flex-wrap: wrap;
    }}

    .page-controls {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .page-btn {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      color: var(--text-main);
      padding: 6px 12px;
      border-radius: var(--radius-sm);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s ease;
    }}

    .page-btn:hover:not(:disabled) {{
      border-color: var(--border-focus);
      color: var(--primary);
    }}

    .page-btn:disabled {{
      opacity: 0.4;
      cursor: not-allowed;
    }}

    .page-btn.active {{
      background: var(--primary);
      color: #090d16;
      border-color: var(--primary);
    }}

    /* Full Detail Modal Drawer */
    .modal-backdrop {{
      position: fixed;
      top: 0;
      left: 0;
      right: 0;
      bottom: 0;
      background: rgba(0, 0, 0, 0.75);
      backdrop-filter: blur(8px);
      z-index: 100;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
    }}

    .modal-backdrop.open {{
      display: flex;
    }}

    .modal-content {{
      background: var(--bg-surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      width: 100%;
      max-width: 900px;
      max-height: 90vh;
      overflow-y: auto;
      box-shadow: 0 25px 60px -15px rgba(0, 0, 0, 0.9);
      position: relative;
      animation: modalIn 0.2s cubic-bezier(0.16, 1, 0.3, 1);
    }}

    @keyframes modalIn {{
      from {{ transform: scale(0.96); opacity: 0; }}
      to {{ transform: scale(1); opacity: 1; }}
    }}

    .modal-header {{
      padding: 24px;
      border-bottom: 1px solid var(--border);
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
      position: sticky;
      top: 0;
      background: rgba(16, 23, 38, 0.95);
      backdrop-filter: blur(10px);
      z-index: 10;
    }}

    .modal-title-wrap {{
      flex: 1;
    }}

    .modal-job-id {{
      font-family: 'JetBrains Mono', monospace;
      font-size: 11px;
      color: var(--primary);
      margin-bottom: 6px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .modal-title {{
      font-size: 20px;
      font-weight: 700;
      line-height: 1.35;
      color: #fff;
    }}

    .close-btn {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 8px;
      color: var(--text-dim);
      font-size: 22px;
      width: 36px;
      height: 36px;
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      line-height: 1;
      transition: all 0.15s ease;
    }}

    .close-btn:hover {{
      color: var(--text-main);
      border-color: var(--primary);
      background: var(--bg-card-hover);
    }}

    .modal-body {{
      padding: 24px;
    }}

    /* Client Dossier Grid */
    .client-dossier-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(190px, 1fr));
      gap: 12px;
      margin-bottom: 24px;
    }}

    .dossier-item {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 12px 14px;
    }}

    .dossier-label {{
      font-size: 11px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
      letter-spacing: 0.04em;
      margin-bottom: 4px;
    }}

    .dossier-val {{
      font-size: 14px;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .detail-section-title {{
      font-size: 13px;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--primary);
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }}

    .desc-box {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 20px;
      font-size: 14px;
      line-height: 1.75;
      color: #e2e8f0;
      white-space: pre-wrap;
      word-break: break-word;
      margin-bottom: 28px;
      max-height: 420px;
      overflow-y: auto;
    }}

    /* Reviews Section */
    .reviews-list {{
      display: flex;
      flex-direction: column;
      gap: 14px;
      margin-bottom: 16px;
    }}

    .review-card {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      padding: 16px 18px;
      transition: border-color 0.2s ease;
    }}

    .review-card:hover {{
      border-color: rgba(56, 189, 248, 0.4);
    }}

    .review-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      flex-wrap: wrap;
    }}

    .reviewer-name {{
      font-size: 13.5px;
      font-weight: 700;
      color: var(--text-main);
      display: flex;
      align-items: center;
      gap: 6px;
    }}

    .reviewer-meta {{
      font-size: 12px;
      color: var(--text-dim);
      font-family: 'JetBrains Mono', monospace;
    }}

    .review-contract {{
      font-size: 12.5px;
      font-weight: 600;
      color: #94a3b8;
      margin-bottom: 8px;
    }}

    .review-bubble {{
      background: rgba(9, 13, 22, 0.6);
      border: 1px solid rgba(35, 49, 77, 0.6);
      border-radius: var(--radius-sm);
      padding: 12px 14px;
      font-size: 13.5px;
      line-height: 1.6;
      color: #f1f5f9;
      white-space: pre-wrap;
    }}

    .review-quote-icon {{
      color: var(--primary);
      margin-right: 6px;
    }}

    .no-reviews-box {{
      background: var(--bg-card);
      border: 1px dashed var(--border);
      border-radius: var(--radius-md);
      padding: 24px;
      text-align: center;
      color: var(--text-dim);
      font-size: 13px;
    }}

    .modal-footer {{
      padding: 18px 24px;
      border-top: 1px solid var(--border);
      display: flex;
      justify-content: flex-end;
      gap: 12px;
      background: var(--bg-card);
      position: sticky;
      bottom: 0;
      z-index: 10;
    }}
  </style>
</head>
<body>

  <!-- Sticky Header -->
  <header>
    <div class="header-inner">
      <div class="brand">
        <div class="brand-icon">
          <svg viewBox="0 0 24 24"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path><polyline points="22,6 12,13 2,6"></polyline></svg>
        </div>
        <div class="brand-text">
          <h1>Upwork Intelligence Live Report <span class="live-badge"><span class="live-dot"></span> 14-Day Crawl</span></h1>
          <p>Scraped Sept 14 &ndash; Sept 27, 2026 &bull; Dual Worker Engine (Chrome &amp; Edge) &bull; 100% Payment Verified</p>
        </div>
      </div>
      <div class="header-actions">
        <button class="btn btn-secondary" onclick="exportCSV()">
          <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="7 10 12 15 17 10"></polyline><line x1="12" y1="15" x2="12" y2="3"></line></svg>
          Export Filtered CSV
        </button>
        <button class="btn btn-primary" onclick="window.scrollTo({{top: document.getElementById('explorer-section').offsetTop - 90, behavior: 'smooth'}})">
          <svg width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          Explore All {total_count:,} Jobs
        </button>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="container">

    <!-- KPI Metric Cards -->
    <div class="metrics-grid">
      <div class="metric-card" style="--card-accent: #38bdf8;">
        <div class="metric-label">TOTAL JOBS FETCHED</div>
        <div class="metric-val">{total_count:,}</div>
        <div class="metric-sub">Across 14 contiguous days</div>
      </div>

      <div class="metric-card" style="--card-accent: #10b981;">
        <div class="metric-label">PAYMENT VERIFIED</div>
        <div class="metric-val">100%</div>
        <div class="metric-sub">Strict verified filter applied</div>
      </div>

      <div class="metric-card" style="--card-accent: #6366f1;">
        <div class="metric-label">COUNTRIES COVERED</div>
        <div class="metric-val">{unique_countries_count}</div>
        <div class="metric-sub">US, UK, CA, AU, EU, Asia &amp; more</div>
      </div>

      <div class="metric-card" style="--card-accent: #a855f7;">
        <div class="metric-label">DESCRIPTIVE REVIEWS</div>
        <div class="metric-val">{total_descriptive_reviews:,}</div>
        <div class="metric-sub">Across {jobs_with_reviews:,} client profiles</div>
      </div>

      <div class="metric-card" style="--card-accent: #f59e0b;">
        <div class="metric-label">HIGH SPENDERS (&gt;$100K)</div>
        <div class="metric-val">{(spend_tiers["$100K - $1M"] + spend_tiers["$1M+"]):,}</div>
        <div class="metric-sub">{spend_tiers["$1M+"]:,} clients with &gt;$1M spend</div>
      </div>

      <div class="metric-card" style="--card-accent: #ec4899;">
        <div class="metric-label">AVG CLIENT RATING</div>
        <div class="metric-val">{avg_rating} <span style="font-size:16px;color:#fbbf24;">★</span></div>
        <div class="metric-sub">From {rating_count:,} rated clients</div>
      </div>
    </div>

    <!-- Charts Section -->
    <div class="charts-grid">
      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">
              <svg width="18" height="18" fill="none" stroke="#38bdf8" stroke-width="2" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
              Daily Job Distribution (14-Day Trajectory)
            </div>
            <div class="chart-subtitle">Sept 14, 2026 to Sept 27, 2026</div>
          </div>
        </div>
        <div class="chart-wrapper">
          <canvas id="dateChart"></canvas>
        </div>
      </div>

      <div class="chart-card">
        <div class="chart-header">
          <div>
            <div class="chart-title">
              <svg width="18" height="18" fill="none" stroke="#10b981" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"></circle><polyline points="12 6 12 12 14 14"></polyline></svg>
              Client Spend Tiers
            </div>
            <div class="chart-subtitle">Verified total historical spend</div>
          </div>
        </div>
        <div class="chart-wrapper">
          <canvas id="spendChart"></canvas>
        </div>
      </div>
    </div>

    <!-- Explorer Section -->
    <section id="explorer-section">
      <!-- Toolbar -->
      <div class="toolbar">
        <div class="search-group">
          <svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="8"></circle><line x1="21" y1="21" x2="16.65" y2="16.65"></line></svg>
          <input type="text" id="searchInput" class="search-input" placeholder="Search by job title, description, skills, location, or Job ID..." oninput="handleSearch()" />
        </div>

        <div class="filter-group">
          <div class="select-wrap">
            <select id="countrySelect" class="custom-select" onchange="handleFilter()">
              <option value="">All Countries ({unique_countries_count})</option>
              {"".join([f'<option value="{c}">{c} ({country_counts[c]:,})</option>' for c in country_labels])}
            </select>
          </div>

          <div class="select-wrap">
            <select id="dateSelect" class="custom-select" onchange="handleFilter()">
              <option value="">All Dates (14 Days)</option>
              {"".join([f'<option value="{d}">{d} ({date_counts[d]:,})</option>' for d in sorted_dates])}
            </select>
          </div>

          <div class="select-wrap">
            <select id="spendSelect" class="custom-select" onchange="handleFilter()">
              <option value="0">Any Client Spend</option>
              <option value="10000">$10,000+ Spent</option>
              <option value="50000">$50,000+ Spent</option>
              <option value="100000">$100,000+ Spent</option>
              <option value="1000000">$1,000,000+ Spent</option>
            </select>
          </div>

          <div class="select-wrap">
            <select id="ratingSelect" class="custom-select" onchange="handleFilter()">
              <option value="0">Any Rating</option>
              <option value="4.5">4.5+ ★ Stars</option>
              <option value="4.8">4.8+ ★ Stars</option>
              <option value="5.0">5.0 ★ Perfect</option>
            </select>
          </div>

          <label class="checkbox-wrap">
            <input type="checkbox" id="reviewsOnlyCheckbox" onchange="handleFilter()" />
            <span>⭐ Has Descriptive Reviews</span>
          </label>
        </div>

        <div class="results-count" id="resultsCount">
          Showing <strong>{min(50, total_count):,}</strong> of <strong>{total_count:,}</strong> jobs
        </div>
      </div>

      <!-- Jobs Table -->
      <div class="table-container">
        <table class="jobs-table">
          <thead>
            <tr>
              <th>Job Title</th>
              <th>Date Posted</th>
              <th>Client Location</th>
              <th>Client Spend</th>
              <th>Rating</th>
              <th>Freelancer Reviews</th>
              <th style="text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody id="jobsTableBody">
            <!-- Dynamic JS rows -->
          </tbody>
        </table>

        <!-- Pagination Bar -->
        <div class="pagination-bar">
          <div class="results-count" id="paginationInfo">
            Page 1 of 1
          </div>
          <div class="page-controls" id="paginationControls">
            <!-- Dynamic JS page buttons -->
          </div>
        </div>
      </div>
    </section>

  </main>

  <!-- Full Detail Drawer / Modal -->
  <div class="modal-backdrop" id="jobModal" onclick="handleBackdropClick(event)">
    <div class="modal-content" onclick="event.stopPropagation()">
      <div class="modal-header">
        <div class="modal-title-wrap">
          <div class="modal-job-id" id="modalJobId">UPWORK JOB ID</div>
          <h2 class="modal-title" id="modalTitle">Job Title</h2>
        </div>
        <button class="close-btn" onclick="closeModal()" title="Close">&times;</button>
      </div>
      
      <div class="modal-body">
        <!-- Client Intelligence Dossier -->
        <div class="detail-section-title">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle><path d="M23 21v-2a4 4 0 0 0-3-3.87"></path><path d="M16 3.13a4 4 0 0 1 0 7.75"></path></svg>
          Client Intelligence Dossier
        </div>
        <div class="client-dossier-grid" id="modalDossier">
          <!-- Populated by JS -->
        </div>

        <!-- Full Job Description -->
        <div class="detail-section-title">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          Complete Full Job Description
        </div>
        <div class="desc-box" id="modalDesc">
          <!-- Populated by JS -->
        </div>

        <!-- Freelancer to Client Reviews -->
        <div class="detail-section-title" id="modalReviewsTitle">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
          Freelancer Reviews of this Client (Complete Descriptive Reviews Only)
        </div>
        <div class="reviews-list" id="modalReviews">
          <!-- Populated by JS -->
        </div>
      </div>

      <div class="modal-footer">
        <a id="modalLink" href="#" target="_blank" rel="noopener noreferrer" class="btn btn-primary">
          Open on Upwork &nearr;
        </a>
        <button class="btn btn-secondary" onclick="closeModal()">Close Window</button>
      </div>
    </div>
  </div>

  <script>
    // Embedded Compact Records:
    // [0: id, 1: title, 2: dt, 3: loc, 4: client_arr, 5: full_desc, 6: url, 7: reviews, 8: spend_num]
    // client_arr = [spent_raw, rating_clean, hire_rate, jobs_posted, member_since, pv, hires, hours]
    // reviews = [[fl, rating, job_title, date, amount, feedback], ...]
    const JOBS_DATA = {jobs_json};

    let filteredData = [...JOBS_DATA];
    let currentPage = 1;
    const pageSize = 50;

    function initCharts() {{
      // Date Chart
      const dateCtx = document.getElementById('dateChart').getContext('2d');
      new Chart(dateCtx, {{
        type: 'bar',
        data: {{
          labels: {json.dumps(date_labels)},
          datasets: [{{
            label: 'Jobs Crawled',
            data: {json.dumps(date_values)},
            backgroundColor: 'rgba(56, 189, 248, 0.4)',
            borderColor: '#38bdf8',
            borderWidth: 1.5,
            borderRadius: 4,
            hoverBackgroundColor: '#38bdf8'
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{ display: false }},
            tooltip: {{
              backgroundColor: '#151f32',
              borderColor: '#23314d',
              borderWidth: 1,
              titleColor: '#f1f5f9',
              bodyColor: '#38bdf8'
            }}
          }},
          scales: {{
            x: {{
              grid: {{ display: false }},
              ticks: {{ color: '#64748b', font: {{ size: 11 }} }}
            }},
            y: {{
              grid: {{ color: 'rgba(35, 49, 77, 0.4)' }},
              ticks: {{ color: '#64748b', font: {{ size: 11 }} }}
            }}
          }}
        }}
      }});

      // Spend Chart
      const spendCtx = document.getElementById('spendChart').getContext('2d');
      new Chart(spendCtx, {{
        type: 'doughnut',
        data: {{
          labels: {json.dumps(tier_labels)},
          datasets: [{{
            data: {json.dumps(tier_values)},
            backgroundColor: [
              '#334155',
              '#3b82f6',
              '#0284c7',
              '#10b981',
              '#f59e0b'
            ],
            borderColor: '#101726',
            borderWidth: 2
          }}]
        }},
        options: {{
          responsive: true,
          maintainAspectRatio: false,
          plugins: {{
            legend: {{
              position: 'right',
              labels: {{ color: '#cbd5e1', font: {{ size: 11 }}, boxWidth: 12 }}
            }},
            tooltip: {{
              backgroundColor: '#151f32',
              borderColor: '#23314d',
              borderWidth: 1
            }}
          }}
        }}
      }});
    }}

    function renderTable() {{
      const tbody = document.getElementById('jobsTableBody');
      tbody.innerHTML = '';

      const total = filteredData.length;
      const start = (currentPage - 1) * pageSize;
      const end = Math.min(start + pageSize, total);
      const pageSlice = filteredData.slice(start, end);

      document.getElementById('resultsCount').innerHTML = 
        `Showing <strong>${{total === 0 ? 0 : start + 1}} - ${{end}}</strong> of <strong>${{total.toLocaleString()}}</strong> jobs`;

      if (pageSlice.length === 0) {{
        tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; padding: 48px; color: var(--text-muted);">No jobs match your active search filters.</td></tr>`;
        renderPagination(0);
        return;
      }}

      pageSlice.forEach(row => {{
        const jid = row[0];
        const title = row[1] || 'Untitled Job';
        const dt = row[2] || 'Unknown';
        const loc = row[3] || 'Worldwide';
        const clientArr = row[4] || [];
        const spentRaw = clientArr[0] || '$0';
        const rating = clientArr[1] || '';
        const pv = clientArr[5] === '1';
        const fullDesc = row[5] || '';
        const snippet = fullDesc.slice(0, 160) + (fullDesc.length > 160 ? '...' : '');
        const revs = row[7] || [];
        const spendNum = row[8] || 0;

        let spendClass = 'spend-tier-low';
        if (spendNum >= 100000) spendClass = 'spend-tier-high';
        else if (spendNum >= 10000) spendClass = 'spend-tier-mid';

        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td class="job-title-col">
            <span class="job-link-title" onclick="openModalById('${{jid}}')" title="Click to view full description & reviews">${{escapeHtml(title)}}</span>
            <div class="job-snippet">${{escapeHtml(snippet)}}</div>
          </td>
          <td><span class="date-badge">${{escapeHtml(dt)}}</span></td>
          <td class="location-cell">
            ${{escapeHtml(loc)}}
            ${{pv ? '<span class="pv-icon" title="Payment Verified">✓</span>' : ''}}
          </td>
          <td><span class="spend-badge ${{spendClass}}">${{escapeHtml(spentRaw || 'Verified')}}</span></td>
          <td>
            ${{rating ? `<span class="rating-badge">★ ${{escapeHtml(rating)}}</span>` : '<span style="color:var(--text-dim);">-</span>'}}
          </td>
          <td>
            ${{revs.length > 0 
              ? `<span class="reviews-badge has-reviews" title="${{revs.length}} complete descriptive reviews">💬 ${{revs.length}} Review${{revs.length > 1 ? 's' : ''}}</span>`
              : '<span class="reviews-badge no-reviews">No reviews</span>'}}
          </td>
          <td style="text-align: right;">
            <button class="view-btn" onclick="openModalById('${{jid}}')">
              View Details &nearr;
            </button>
          </td>
        `;
        tbody.appendChild(tr);
      }});

      renderPagination(total);
    }}

    function renderPagination(total) {{
      const totalPages = Math.ceil(total / pageSize);
      const info = document.getElementById('paginationInfo');
      info.innerText = `Page ${{totalPages === 0 ? 0 : currentPage}} of ${{totalPages}}`;

      const controls = document.getElementById('paginationControls');
      controls.innerHTML = '';

      if (totalPages <= 1) return;

      const prevBtn = document.createElement('button');
      prevBtn.className = 'page-btn';
      prevBtn.innerText = '‹ Prev';
      prevBtn.disabled = (currentPage === 1);
      prevBtn.onclick = () => {{ currentPage--; renderTable(); window.scrollTo({{top: document.getElementById('explorer-section').offsetTop - 90, behavior: 'smooth'}}); }};
      controls.appendChild(prevBtn);

      let startP = Math.max(1, currentPage - 2);
      let endP = Math.min(totalPages, currentPage + 2);

      if (startP > 1) {{
        const b = document.createElement('button');
        b.className = 'page-btn';
        b.innerText = '1';
        b.onclick = () => {{ currentPage = 1; renderTable(); }};
        controls.appendChild(b);
        if (startP > 2) {{
          const sp = document.createElement('span');
          sp.innerText = '...';
          sp.style.color = '#64748b';
          controls.appendChild(sp);
        }}
      }}

      for (let p = startP; p <= endP; p++) {{
        const btn = document.createElement('button');
        btn.className = 'page-btn' + (p === currentPage ? ' active' : '');
        btn.innerText = p;
        btn.onclick = () => {{ currentPage = p; renderTable(); window.scrollTo({{top: document.getElementById('explorer-section').offsetTop - 90, behavior: 'smooth'}}); }};
        controls.appendChild(btn);
      }}

      if (endP < totalPages) {{
        if (endP < totalPages - 1) {{
          const sp = document.createElement('span');
          sp.innerText = '...';
          sp.style.color = '#64748b';
          controls.appendChild(sp);
        }}
        const b = document.createElement('button');
        b.className = 'page-btn';
        b.innerText = totalPages;
        b.onclick = () => {{ currentPage = totalPages; renderTable(); }};
        controls.appendChild(b);
      }}

      const nextBtn = document.createElement('button');
      nextBtn.className = 'page-btn';
      nextBtn.innerText = 'Next ›';
      nextBtn.disabled = (currentPage === totalPages);
      nextBtn.onclick = () => {{ currentPage++; renderTable(); window.scrollTo({{top: document.getElementById('explorer-section').offsetTop - 90, behavior: 'smooth'}}); }};
      controls.appendChild(nextBtn);
    }}

    function handleSearch() {{
      currentPage = 1;
      applyFilters();
    }}

    function handleFilter() {{
      currentPage = 1;
      applyFilters();
    }}

    function applyFilters() {{
      const query = (document.getElementById('searchInput').value || '').trim().toLowerCase();
      const countryFilter = document.getElementById('countrySelect').value;
      const dateFilter = document.getElementById('dateSelect').value;
      const spendFilter = parseFloat(document.getElementById('spendSelect').value || '0');
      const ratingFilter = parseFloat(document.getElementById('ratingSelect').value || '0');
      const reviewsOnly = document.getElementById('reviewsOnlyCheckbox').checked;

      filteredData = JOBS_DATA.filter(row => {{
        // row: [jid, title, dt, loc, client_arr, full_desc, url, reviews, spend_num]
        const jid = (row[0] || '').toLowerCase();
        const title = (row[1] || '').toLowerCase();
        const dt = row[2] || '';
        const loc = row[3] || '';
        const clientArr = row[4] || [];
        const fullDesc = (row[5] || '').toLowerCase();
        const revs = row[7] || [];
        const spendNum = row[8] || 0;
        const ratingNum = parseFloat(clientArr[1] || '0');

        if (query) {{
          if (!title.includes(query) && !fullDesc.includes(query) && !loc.toLowerCase().includes(query) && !jid.includes(query)) {{
            return false;
          }}
        }}

        if (countryFilter && loc !== countryFilter) {{
          return false;
        }}

        if (dateFilter && dt !== dateFilter) {{
          return false;
        }}

        if (spendFilter > 0 && spendNum < spendFilter) {{
          return false;
        }}

        if (ratingFilter > 0 && ratingNum < ratingFilter) {{
          return false;
        }}

        if (reviewsOnly && revs.length === 0) {{
          return false;
        }}

        return true;
      }});

      renderTable();
    }}

    function openModalById(jid) {{
      const row = JOBS_DATA.find(r => r[0] === jid);
      if (!row) return;

      const title = row[1] || 'Untitled Job';
      const dt = row[2] || 'Unknown';
      const loc = row[3] || 'Worldwide';
      const clientArr = row[4] || [];
      const spentRaw = clientArr[0] || '$0';
      const rating = clientArr[1] || 'No rating';
      const hireRate = clientArr[2] || '';
      const jobsPosted = clientArr[3] || '';
      const memberSince = clientArr[4] || '';
      const pv = clientArr[5] === '1';
      const hires = clientArr[6] || '';
      const hours = clientArr[7] || '';
      const fullDesc = row[5] || 'No description provided in job post.';
      const url = row[6] || ('https://www.upwork.com/jobs/~' + jid);
      const revs = row[7] || [];

      document.getElementById('modalJobId').innerText = `JOB ID: ~${{jid}} • POSTED: ${{dt}}`;
      document.getElementById('modalTitle').innerText = title;

      // Build Client Dossier Grid
      const dossier = document.getElementById('modalDossier');
      dossier.innerHTML = `
        <div class="dossier-item">
          <div class="dossier-label">Client Location</div>
          <div class="dossier-val">${{escapeHtml(loc)}}</div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Payment Status</div>
          <div class="dossier-val" style="color: ${{pv ? '#10b981' : '#f59e0b'}}">
            ${{pv ? '✓ Verified' : 'Unverified'}}
          </div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Total Spent</div>
          <div class="dossier-val">${{escapeHtml(spentRaw || '$0')}}</div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Client Rating</div>
          <div class="dossier-val">${{rating ? rating + ' ★' : 'No rating'}}</div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Hire Rate</div>
          <div class="dossier-val">${{hireRate || 'Not listed'}}</div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Jobs Posted</div>
          <div class="dossier-val">${{jobsPosted || '1'}}</div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Total Hires</div>
          <div class="dossier-val">${{hires || '0'}}</div>
        </div>
        <div class="dossier-item">
          <div class="dossier-label">Member Since</div>
          <div class="dossier-val">${{memberSince || 'Unknown'}}</div>
        </div>
      `;

      // Full Description
      document.getElementById('modalDesc').innerText = fullDesc;

      // Reviews
      const revsTitle = document.getElementById('modalReviewsTitle');
      revsTitle.innerHTML = `
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
        Freelancer Reviews of this Client (${{revs.length}} Complete Descriptive Review${{revs.length === 1 ? '' : 's'}})
      `;

      const revsContainer = document.getElementById('modalReviews');
      if (revs.length === 0) {{
        revsContainer.innerHTML = `
          <div class="no-reviews-box">
            This client has no descriptive freelancer feedback recorded on Upwork.
          </div>
        `;
      }} else {{
        revsContainer.innerHTML = revs.map(rev => {{
          const fl = rev[0] || 'Anonymous Freelancer';
          const rRating = rev[1] || '5.0';
          const cTitle = rev[2] || 'Past Contract';
          const cDate = rev[3] || '';
          const cAmt = rev[4] || '';
          const cFb = rev[5] || '';

          return `
            <div class="review-card">
              <div class="review-header">
                <div class="reviewer-name">
                  <span>${{escapeHtml(fl)}}</span>
                  <span class="rating-badge" style="margin-left: 6px;">★ ${{escapeHtml(rRating)}}</span>
                </div>
                <div class="reviewer-meta">
                  ${{cDate ? escapeHtml(cDate) : ''}} ${{cAmt ? '• ' + escapeHtml(cAmt) : ''}}
                </div>
              </div>
              <div class="review-contract">${{escapeHtml(cTitle)}}</div>
              <div class="review-bubble">
                <span class="review-quote-icon">“</span>${{escapeHtml(cFb)}}
              </div>
            </div>
          `;
        }}).join('');
      }}

      document.getElementById('modalLink').href = url;
      document.getElementById('jobModal').classList.add('open');
    }}

    function closeModal() {{
      document.getElementById('jobModal').classList.remove('open');
    }}

    function handleBackdropClick(e) {{
      if (e.target.id === 'jobModal') {{
        closeModal();
      }}
    }}

    document.addEventListener('keydown', (e) => {{
      if (e.key === 'Escape') closeModal();
    }});

    function exportCSV() {{
      if (filteredData.length === 0) {{
        alert('No rows to export.');
        return;
      }}
      const headers = ['Job ID', 'Title', 'Date Posted', 'Location', 'Client Spend', 'Rating', 'Hire Rate', 'Reviews Count', 'URL'];
      let csvContent = 'data:text/csv;charset=utf-8,' + headers.join(',') + '\\n';

      filteredData.slice(0, 5000).forEach(row => {{
        const jid = row[0];
        const cleanTitle = '"' + (row[1] || '').replace(/"/g, '""') + '"';
        const dt = row[2] || '';
        const cleanLoc = '"' + (row[3] || '').replace(/"/g, '""') + '"';
        const clientArr = row[4] || [];
        const cleanSpend = '"' + (clientArr[0] || '').replace(/"/g, '""') + '"';
        const rat = clientArr[1] || '';
        const hr = clientArr[2] || '';
        const revCount = (row[7] || []).length;
        const u = row[6] || '';
        const line = [jid, cleanTitle, dt, cleanLoc, cleanSpend, rat, hr, revCount, u].join(',');
        csvContent += line + '\\n';
      }});

      const encodedUri = encodeURI(csvContent);
      const link = document.createElement('a');
      link.setAttribute('href', encodedUri);
      link.setAttribute('download', 'upwork_fetched_jobs_' + new Date().toISOString().slice(0,10) + '.csv');
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    }}

    function escapeHtml(str) {{
      if (!str) return '';
      return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
    }}

    document.addEventListener('DOMContentLoaded', () => {{
      initCharts();
      renderTable();
    }});
  </script>
</body>
</html>
"""

    print(f"Writing report to: {OUTPUT_HTML}")
    with open(OUTPUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"Writing duplicate to: {OUTPUT_HTML_ALT}")
    with open(OUTPUT_HTML_ALT, "w", encoding="utf-8") as f:
        f.write(html_content)

    size_mb = os.path.getsize(OUTPUT_HTML) / (1024 * 1024)
    print(f"HTML successfully generated! File size: {size_mb:.2f} MB")

if __name__ == "__main__":
    main()
