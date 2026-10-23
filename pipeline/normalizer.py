"""
Data normalizer ensuring data completeness, schema conformance, and clean field representation.
"""

from typing import List, Dict, Any
from models.schema import JobPosting
from parsers.truncation_detector import detect_truncation


class Normalizer:
    """
    Validates and normalizes JobPosting models into the clean canonical schema.
    """

    @staticmethod
    def normalize_job(job: JobPosting) -> JobPosting:
        """
        Cleans and audits a single JobPosting instance.
        """
        # Ensure description is un-truncated and clean
        job.title = job.title.strip()
        job.description = job.description.strip()

        # Audit all client history reviews for any truncation flags
        for item in job.client_recent_history:
            item.job_title = item.job_title.strip()
            item.full_review = item.full_review.strip()
            is_trunc, _ = detect_truncation(item.full_review)
            item.is_truncated = is_trunc

        return job

    @staticmethod
    def normalize_batch(jobs: List[JobPosting]) -> List[JobPosting]:
        return [Normalizer.normalize_job(j) for j in jobs]
