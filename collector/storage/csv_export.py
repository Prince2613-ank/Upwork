"""
Section 12: CSV Export Engine.
Exports jobs.csv and client_history.csv for tabular preview and analysis.
"""

import csv
from pathlib import Path
from typing import List, Optional
from collector.models.schema import CollectedJob
from collector.config.settings import settings


def export_jobs_csv(
    jobs: List[CollectedJob],
    output_dir: Optional[Path] = None,
    filename: str = "jobs.csv",
    merge: bool = True,
) -> Path:
    """Exports flattened jobs.csv matching Section 12."""
    target_dir = output_dir or settings.output_path
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / filename

    fieldnames = [
        "job_id",
        "job_url",
        "job_title",
        "posted_at",
        "posted_raw",
        "client_location",
        "client_profile_url",
        "reviews_anchor",
        "raw_html_file",
        "job_type",
        "experience_level",
        "budget",
        "hourly_min",
        "hourly_max",
        "fixed_price",
        "skills",
        "proposals",
        "payment_verified",
        "client_rating",
        "client_total_spent",
        "jobs_posted",
        "hire_rate",
        "total_hires",
        "active_hires",
        "hours_billed",
        "member_since",
        "history_count",
        "description",
    ]

    existing_rows = {}
    if merge and out_path.exists():
        try:
            with open(out_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    jid = r.get("job_id") or r.get("job_url")
                    if jid:
                        existing_rows[jid] = r
        except Exception:
            pass

    for j in jobs:
        links = j.links or {}
        row = {
            "job_id": j.job_id,
            "job_url": j.job_url,
            "job_title": j.job_title,
            "posted_at": j.posted_at,
            "posted_raw": j.posted_raw,
            "client_location": j.client_location,
            "client_profile_url": links.get("client_profile_url", ""),
            "reviews_anchor": links.get("reviews_anchor", ""),
            "raw_html_file": links.get("raw_html_file", ""),
            "job_type": j.job.job_type,
            "experience_level": j.job.experience_level,
            "budget": j.job.budget,
            "hourly_min": j.job.hourly_min,
            "hourly_max": j.job.hourly_max,
            "fixed_price": j.job.fixed_price,
            "skills": "; ".join(j.job.skills),
            "proposals": j.job.proposals,
            "payment_verified": j.client.payment_verified,
            "client_rating": j.client.rating,
            "client_total_spent": j.client.total_spent,
            "jobs_posted": j.client.jobs_posted,
            "hire_rate": j.client.hire_rate,
            "total_hires": j.client.total_hires,
            "active_hires": j.client.active_hires,
            "hours_billed": j.client.hours_billed,
            "member_since": j.client.member_since,
            "history_count": len(j.client_recent_history),
            "description": j.job.description,
        }
        jid = j.job_id or j.job_url
        if jid:
            existing_rows[jid] = row

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in existing_rows.values():
            writer.writerow(r)

    return out_path


def export_client_history_csv(
    jobs: List[CollectedJob],
    output_dir: Optional[Path] = None,
    filename: str = "client_history.csv",
    merge: bool = True,
) -> Path:
    """Exports client_history.csv matching Section 12, optionally merging across runs."""
    target_dir = output_dir or settings.output_path
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / filename

    fieldnames = [
        "parent_job_id",
        "parent_job_url",
        "parent_job_title",
        "client_profile_url",
        "raw_html_file",
        "client_location",
        "history_job_title",
        "history_job_url",
        "date",
        "duration",
        "payment_type",
        "amount",
        "rating",
        "freelancer_name",
        "feedback",
        "feedback_full",
    ]

    existing_items = {}
    if merge and out_path.exists():
        try:
            with open(out_path, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for r in reader:
                    key = (r.get("parent_job_id", ""), r.get("history_job_title", ""), r.get("date", ""))
                    existing_items[key] = r
        except Exception:
            pass

    for j in jobs:
        links = j.links or {}
        for h in j.client_recent_history:
            item = {
                "parent_job_id": j.job_id,
                "parent_job_url": j.job_url,
                "parent_job_title": j.job_title,
                "client_profile_url": links.get("client_profile_url", ""),
                "raw_html_file": links.get("raw_html_file", ""),
                "client_location": j.client_location,
                "history_job_title": h.job_title,
                "history_job_url": h.job_url,
                "date": h.date,
                "duration": h.duration,
                "payment_type": h.payment_type,
                "amount": h.amount,
                "rating": h.rating,
                "freelancer_name": h.freelancer_name,
                "feedback": h.feedback,
                "feedback_full": h.feedback_full,
            }
            key = (j.job_id, h.job_title, h.date)
            existing_items[key] = item

    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in existing_items.values():
            writer.writerow(r)

    return out_path
