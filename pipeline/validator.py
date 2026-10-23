"""
Validation engine and report generator for collection runs.
Fulfills Requirement 14: Generates authoritative validation reports.
"""

from typing import List, Optional
from models.schema import JobPosting, ValidationReport
from parsers.truncation_detector import detect_truncation


class RunValidator:
    """
    Validates a set of collected jobs and produces a complete quality report.
    """

    @staticmethod
    def audit_run(
        run_id: str,
        source_type: str,
        jobs: List[JobPosting],
        jobs_requested: int,
        duplicate_jobs_removed: int = 0,
        pages_processed: int = 1,
        errors_count: int = 0,
        retries_count: int = 0,
        rate_limit_responses: int = 0,
        cutoff_date: Optional[str] = None,
    ) -> ValidationReport:
        total_collected = len(jobs)

        # 1. Full descriptions count
        full_desc_count = sum(1 for j in jobs if j.description and len(j.description.strip()) > 30)

        # 2. About client count
        about_client_count = sum(
            1 for j in jobs if j.client.location or j.client.total_spent or j.client.rating is not None
        )

        # 3. Recent history count
        recent_history_count = sum(1 for j in jobs if len(j.client_recent_history) > 0)

        # 4. Reviews audit
        total_reviews = 0
        complete_reviews = 0
        suspected_truncated = 0

        for j in jobs:
            for item in j.client_recent_history:
                if item.full_review:
                    total_reviews += 1
                    is_trunc, reason = detect_truncation(item.full_review)
                    if is_trunc:
                        suspected_truncated += 1
                    else:
                        complete_reviews += 1

        # 5. Oldest and newest job date
        sorted_dates = sorted([j.posted_at for j in jobs if j.posted_at])
        oldest_date = sorted_dates[0] if sorted_dates else None
        newest_date = sorted_dates[-1] if sorted_dates else None

        report = ValidationReport(
            run_id=run_id,
            source_type=source_type,
            jobs_requested=jobs_requested,
            jobs_collected=total_collected,
            duplicate_jobs_removed=duplicate_jobs_removed,
            full_descriptions_count=full_desc_count,
            full_descriptions_ratio=f"{full_desc_count}/{total_collected}" if total_collected else "0/0",
            about_client_count=about_client_count,
            about_client_ratio=f"{about_client_count}/{total_collected}" if total_collected else "0/0",
            recent_history_count=recent_history_count,
            recent_history_ratio=f"{recent_history_count}/{total_collected}" if total_collected else "0/0",
            total_reviews_collected=total_reviews,
            complete_reviews_count=complete_reviews,
            suspected_truncated_reviews_count=suspected_truncated,
            oldest_job_date=oldest_date,
            newest_job_date=newest_date,
            cutoff_date=cutoff_date,
            pages_processed=pages_processed,
            errors_count=errors_count,
            retries_count=retries_count,
            rate_limit_responses=rate_limit_responses,
        )

        return report
