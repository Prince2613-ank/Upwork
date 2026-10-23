"""
Orchestrator for paginated, date-cutoff governed Upwork market intelligence collection.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
from config import DATE_WINDOW_DAYS
from models.schema import JobPosting, RunCheckpoint, ValidationReport
from sources.base import BaseDataSource
from parsers.job_parser import parse_job_posting_page
from parsers.date_parser import parse_upwork_date, is_older_than_cutoff, get_cutoff_datetime
from .deduplicator import Deduplicator
from .checkpoint import CheckpointManager
from .normalizer import Normalizer
from .exporter import Exporter
from .validator import RunValidator

logger = logging.getLogger(__name__)


class Collector:
    """
    Coordinates data collection, date cutoff stopping, deduplication,
    checkpointing, normalization, and export.
    """

    def __init__(
        self,
        data_source: BaseDataSource,
        run_id: Optional[str] = None,
        date_window_days: int = DATE_WINDOW_DAYS,
        checkpoint_mgr: Optional[CheckpointManager] = None,
        exporter: Optional[Exporter] = None,
    ):
        self.data_source = data_source
        self.run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        self.date_window_days = date_window_days
        self.checkpoint_mgr = checkpoint_mgr or CheckpointManager()
        self.exporter = exporter or Exporter()
        self.normalizer = Normalizer()
        self.deduplicator = Deduplicator()

        self.collected_jobs: List[JobPosting] = []
        self.pages_processed = 0
        self.errors_count = 0
        self.retries_count = 0
        self.rate_limit_responses = 0

    def run(
        self,
        max_jobs: Optional[int] = None,
        resume: bool = False,
        source_type: str = "mock",
    ) -> Tuple[List[JobPosting], ValidationReport]:
        """
        Executes the collection process.
        Stops when:
          1. Job date is older than cutoff_datetime (Date requirement)
          2. max_jobs target is reached (e.g. 5 for POC, 50 for test)
          3. No more search pages are available
        """
        start_time = datetime.now(timezone.utc)
        cutoff_dt = get_cutoff_datetime(self.date_window_days, reference_time=start_time)
        cutoff_iso = cutoff_dt.isoformat()

        start_page = 1
        if resume:
            ckpt = self.checkpoint_mgr.load_latest_checkpoint()
            if ckpt and ckpt.status != "completed":
                logger.info(f"Resuming run {ckpt.run_id} from page {ckpt.last_page + 1}...")
                self.run_id = ckpt.run_id
                start_page = ckpt.last_page + 1
                self.deduplicator = Deduplicator(existing_ids=ckpt.collected_job_ids)

        logger.info(
            f"Starting collection run {self.run_id} | Cutoff: {cutoff_iso} "
            f"({self.date_window_days} days back) | Target: {max_jobs or 'All within date cutoff'}"
        )

        page = start_page
        cutoff_reached = False
        limit_reached = False

        while True:
            logger.info(f"--- Processing Search Page {page} ---")
            try:
                summaries, has_more = self.data_source.fetch_search_page(page=page)
            except Exception as e:
                self.errors_count += 1
                logger.error(f"Error fetching search page {page}: {e}")
                break

            if not summaries:
                logger.info(f"No more jobs returned on page {page}.")
                break

            self.pages_processed += 1

            for item in summaries:
                jid = item["job_id"]
                jurl = item["job_url"]

                # Deduplication check
                if not self.deduplicator.register(jid):
                    logger.info(f"Skipping duplicate job {jid}")
                    continue

                # Fetch full details
                try:
                    raw_content = self.data_source.fetch_job_details(jid, jurl)
                    # Requirement 8: Save raw data
                    self.exporter.save_raw_job(self.run_id, jid, raw_content)
                except Exception as e:
                    self.errors_count += 1
                    logger.error(f"Error fetching full details for {jid}: {e}")
                    continue

                # Parse into model
                try:
                    job = parse_job_posting_page(
                        raw_content,
                        job_url=jurl,
                        search_page=page,
                        source_type=source_type,
                    )
                    job = self.normalizer.normalize_job(job)
                except Exception as e:
                    self.errors_count += 1
                    logger.error(f"Error parsing job {jid}: {e}")
                    continue

                # Check Date Cutoff Stopping Condition (Requirement 3)
                job_dt, _ = parse_upwork_date(job.posted_raw or job.posted_at, reference_time=start_time)
                if is_older_than_cutoff(job_dt, cutoff_dt):
                    logger.info(
                        f"Job {jid} posted at {job.posted_at} is older than cutoff {cutoff_iso}. "
                        f"DATE CUTOFF REACHED. Halting collection."
                    )
                    cutoff_reached = True
                    break

                self.collected_jobs.append(job)
                logger.info(
                    f"[{len(self.collected_jobs)}] Collected '{job.title[:45]}...' "
                    f"| ID: {job.job_id} | Client: {job.client.location or 'Unknown'} "
                    f"| History items: {len(job.client_recent_history)}"
                )

                if max_jobs and len(self.collected_jobs) >= max_jobs:
                    logger.info(f"Target count of {max_jobs} jobs reached.")
                    limit_reached = True
                    break

            # Save atomic checkpoint after each page (Requirement 11)
            oldest_dt = min([j.posted_at for j in self.collected_jobs]) if self.collected_jobs else None
            newest_dt = max([j.posted_at for j in self.collected_jobs]) if self.collected_jobs else None
            status_str = "completed" if (cutoff_reached or limit_reached or not has_more) else "running"

            checkpoint = RunCheckpoint(
                run_id=self.run_id,
                started_at=start_time.isoformat(),
                last_updated_at=datetime.now(timezone.utc).isoformat(),
                last_page=page,
                last_job_id=self.collected_jobs[-1].job_id if self.collected_jobs else None,
                oldest_job_date=oldest_dt,
                newest_job_date=newest_dt,
                cutoff_date=cutoff_iso,
                jobs_collected=len(self.collected_jobs),
                pages_processed=self.pages_processed,
                status=status_str,
                collected_job_ids=list(self.deduplicator.get_seen_ids()),
            )
            self.checkpoint_mgr.save_checkpoint(checkpoint)

            if cutoff_reached or limit_reached or not has_more:
                break

            page += 1

        # Persistence & Exports
        self.exporter.save_processed_jobs(self.run_id, self.collected_jobs)
        self.exporter.export_claude_ready(self.collected_jobs)

        # Audit & Validation Report (Requirement 14)
        report = RunValidator.audit_run(
            run_id=self.run_id,
            source_type=source_type,
            jobs=self.collected_jobs,
            jobs_requested=max_jobs or len(self.collected_jobs),
            duplicate_jobs_removed=self.deduplicator.duplicates_removed,
            pages_processed=self.pages_processed,
            errors_count=self.errors_count,
            retries_count=self.retries_count,
            rate_limit_responses=self.rate_limit_responses,
            cutoff_date=cutoff_iso,
        )

        return self.collected_jobs, report
