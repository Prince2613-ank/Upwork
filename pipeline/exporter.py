"""
Export engine for raw snapshots, processed datasets, and Claude-ready exports (JSON + CSV).
"""

import csv
import json
import logging
from pathlib import Path
from typing import List, Dict, Any
from config import RAW_DATA_DIR, PROCESSED_DATA_DIR, EXPORTS_DIR
from models.schema import JobPosting

logger = logging.getLogger(__name__)


class Exporter:
    """
    Handles persisting raw data, processed JSON data, and Claude-ready exports.
    """

    def __init__(
        self,
        raw_dir: Path = RAW_DATA_DIR,
        processed_dir: Path = PROCESSED_DATA_DIR,
        exports_dir: Path = EXPORTS_DIR,
    ):
        self.raw_dir = Path(raw_dir)
        self.processed_dir = Path(processed_dir)
        self.exports_dir = Path(exports_dir)
        for d in [self.raw_dir, self.processed_dir, self.exports_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def save_raw_job(self, run_id: str, job_id: str, raw_content: str, extension: str = "html") -> Path:
        """
        Saves the exact raw HTML or JSON returned by the data source.
        Ensures Requirement 8: "DO NOT LOSE RAW DATA".
        """
        run_raw_dir = self.raw_dir / run_id
        run_raw_dir.mkdir(parents=True, exist_ok=True)
        # Sanitize filename
        safe_id = job_id.replace("~", "").replace("/", "_")
        file_path = run_raw_dir / f"{safe_id}.{extension}"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(raw_content)
        return file_path

    def save_processed_jobs(self, run_id: str, jobs: List[JobPosting]) -> Path:
        """
        Saves the normalized dataset to data/processed/{run_id}_jobs.json.
        """
        out_file = self.processed_dir / f"{run_id}_jobs.json"
        data = [j.model_dump() for j in jobs]
        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Saved {len(jobs)} normalized jobs to {out_file}")
        return out_file

    def export_claude_ready(
        self,
        jobs: List[JobPosting],
        canonical_name: str = "upwork_last_month",
    ) -> Dict[str, Path]:
        """
        Exports the final dataset in canonical Claude-ready JSON and CSV formats.
        Requirement 15:
            data/exports/upwork_last_month.json (canonical)
            data/exports/upwork_last_month.csv (convenience)
        """
        json_path = self.exports_dir / f"{canonical_name}.json"
        csv_path = self.exports_dir / f"{canonical_name}.csv"

        # 1. Canonical JSON Export
        data = [j.model_dump() for j in jobs]
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        logger.info(f"Exported canonical Claude-ready JSON: {json_path}")

        # 2. Convenience CSV Export (flattened with summary stats)
        csv_fieldnames = [
            "job_id",
            "job_url",
            "title",
            "posted_at",
            "posted_raw",
            "budget_type",
            "budget_amount",
            "min_hourly",
            "max_hourly",
            "currency",
            "experience_level",
            "duration",
            "skills",
            "category",
            "proposals",
            "client_location",
            "client_payment_verified",
            "client_rating",
            "client_reviews_count",
            "client_total_spent",
            "client_jobs_posted",
            "client_total_hires",
            "client_hire_rate",
            "client_member_since",
            "history_items_count",
            "full_description",
            "history_reviews_summary",
        ]

        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=csv_fieldnames)
            writer.writeheader()
            for j in jobs:
                # Combine reviews summary
                reviews_summary = " | ".join(
                    [f"[{h.date}] {h.job_title}: {h.full_review}" for h in j.client_recent_history if h.full_review]
                )
                writer.writerow(
                    {
                        "job_id": j.job_id,
                        "job_url": j.job_url,
                        "title": j.title,
                        "posted_at": j.posted_at,
                        "posted_raw": j.posted_raw,
                        "budget_type": j.budget.type,
                        "budget_amount": j.budget.amount,
                        "min_hourly": j.budget.min_hourly,
                        "max_hourly": j.budget.max_hourly,
                        "currency": j.budget.currency,
                        "experience_level": j.experience_level or "",
                        "duration": j.duration or "",
                        "skills": ", ".join(j.skills),
                        "category": j.category or "",
                        "proposals": j.proposals or "",
                        "client_location": j.client.location or "",
                        "client_payment_verified": j.client.payment_verified,
                        "client_rating": j.client.rating,
                        "client_reviews_count": j.client.reviews_count,
                        "client_total_spent": j.client.total_spent or "",
                        "client_jobs_posted": j.client.jobs_posted,
                        "client_total_hires": j.client.total_hires,
                        "client_hire_rate": j.client.hire_rate,
                        "client_member_since": j.client.member_since or "",
                        "history_items_count": len(j.client_recent_history),
                        "full_description": j.description,
                        "history_reviews_summary": reviews_summary,
                    }
                )
        logger.info(f"Exported convenience CSV: {csv_path}")

        return {"json": json_path, "csv": csv_path}
