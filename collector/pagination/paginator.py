"""
Section 9: Dynamic Pagination Manager.
Navigates across Upwork search pages dynamically, evaluates the oldest job on each page,
and manages the date-based boundary condition.
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Tuple, Optional
from collector.pagination.date_boundary import parse_upwork_date, is_older_than_cutoff, get_cutoff_datetime
from collector.logging.logger import logger


class Paginator:
    """Manages search page transitions and dynamic date boundary halting."""

    def __init__(
        self,
        cutoff_dt: datetime,
        min_age_days: Optional[float] = None,
        max_age_days: Optional[float] = None,
    ):
        self.cutoff_dt = cutoff_dt
        self.min_age_days = min_age_days
        self.max_age_days = max_age_days
        self.current_page: int = 1
        self.oldest_seen_dt: Optional[datetime] = None
        self.newest_seen_dt: Optional[datetime] = None

    def evaluate_page_jobs(
        self,
        job_summaries: List[Dict[str, Any]],
        start_time: datetime,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """
        Evaluates jobs on a page against cutoff_dt, min_age_days, and max_age_days:
        - Filters out jobs newer than min_age_days or older than max_age_days/cutoff
        - Records oldest job on the page
        - Returns (valid_in_range_jobs, should_stop_pagination)
        """
        if not job_summaries:
            return [], True

        in_range_jobs = []
        # Check each job against age window
        past_max_count = 0
        for item in job_summaries:
            posted_str = item.get("posted_time") or item.get("normalized_posted_datetime") or ""
            dt, _ = parse_upwork_date(posted_str, reference_time=start_time)

            if self.newest_seen_dt is None or dt > self.newest_seen_dt:
                self.newest_seen_dt = dt
            if self.oldest_seen_dt is None or dt < self.oldest_seen_dt:
                self.oldest_seen_dt = dt

            age_days = max(0.0, (start_time - dt).total_seconds() / 86400.0)

            # Check if this item is past the max cutoff
            effective_max_days = self.max_age_days if self.max_age_days is not None else 31.0
            if age_days > effective_max_days or is_older_than_cutoff(dt, self.cutoff_dt):
                past_max_count += 1
            else:
                # 1. Skip if too new (younger than min_age_days)
                if self.min_age_days is not None and age_days < self.min_age_days:
                    continue
                # In range!
                in_range_jobs.append(item)

        # Halt pagination when 100% of jobs or >=85% of jobs (with at least 10 cards) are older than max age
        should_stop = False
        total = len(job_summaries)
        if total > 0 and (past_max_count == total or (total >= 10 and (past_max_count / total) >= 0.85)):
            limit_desc = f"{effective_max_days:.1f} days"
            logger.info(f"Target date boundary reached: {past_max_count}/{total} jobs on page are older than {limit_desc}. Advancing.")
            should_stop = True

        return in_range_jobs, should_stop
