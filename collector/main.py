"""
Central Collector Orchestrator.
Coordinates Browser / Source, Parsers, Date-Boundary Pagination,
Deduplication, Checkpoints, Exports, and the Section 20 3-Job Test Mode.
"""

import json
import time
import threading
import concurrent.futures
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from collector.config.settings import settings
from collector.logging.logger import logger, error_logger
from collector.models.schema import (
    CollectedJob,
    ScrapeRunMeta,
    ScrapeDataset,
    CheckpointData,
)
from collector.extraction.search_parser import parse_search_page_html
from collector.extraction.job_parser import parse_job_detail_page
from collector.pagination.date_boundary import get_cutoff_datetime, parse_upwork_date, is_older_than_cutoff
from collector.pagination.paginator import Paginator
from collector.storage.database import JobDatabase
from collector.storage.json_export import export_jobs_json, export_run_summary_json
from collector.storage.csv_export import export_jobs_csv, export_client_history_csv
from collector.checkpoint.checkpoint_manager import CheckpointManager
from collector.browser.browser_manager import BrowserManager, SecurityRestrictionError
from collector.browser.page_manager import PageManager
from collector.fixtures import (
    generate_mock_search_page_html,
    generate_mock_job_detail_html,
    MOCK_JOBS_CATALOG,
)


class CollectorEngine:
    PARALLEL_TABS = 3  # Number of parallel browser tabs for multi-threaded job detail fetching

    def __init__(self, source_mode: str = "auto", new_tab: bool = False):
        self.source_mode = source_mode  # "browser", "mock", "auto"
        self.new_tab = new_tab
        self.checkpoint_mgr = CheckpointManager()
        self.db = JobDatabase()
        self.browser_mgr: Optional[BrowserManager] = None
        self.page_mgr: Optional[PageManager] = None
        self.is_paused: bool = False
        self.is_stopped: bool = False
        self._db_lock = threading.Lock()  # Thread-safe DB writes

    def _append_live_feed(self, job: CollectedJob):
        """
        Appends the fully-parsed job (minus raw_html) to a JSONL feed so a
        separate dashboard process can show complete data for in-progress
        pages instead of waiting for the once-per-page jobs.json export.
        """
        try:
            feed_path = settings.output_path / "logs" / "live_feed.jsonl"
            feed_path.parent.mkdir(parents=True, exist_ok=True)
            record = job.model_dump(exclude={"raw_html"})
            line = json.dumps(record, default=str) + "\n"
            with open(feed_path, "a", encoding="utf-8") as f:
                f.write(line)
            port = "9222"
            if "9223" in getattr(settings, "cdp_url", ""):
                port = "9223"
            elif "9222" in getattr(settings, "cdp_url", ""):
                port = "9222"
            port_feed = settings.output_path / "logs" / f"live_feed_{port}.jsonl"
            with open(port_feed, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception as e:
            logger.debug(f"Live feed append note: {e}")

    def _init_browser_if_needed(self) -> bool:
        """Initializes browser connection if source_mode is browser or auto."""
        if self.source_mode == "mock":
            return False

        if self.browser_mgr and self.browser_mgr.page and self.page_mgr:
            try:
                if not self.browser_mgr.page.is_closed():
                    return True
            except Exception:
                pass

        try:
            self.browser_mgr = BrowserManager(new_tab=self.new_tab)
            page = self.browser_mgr.start()
            self.page_mgr = PageManager(page)
            return True
        except Exception as e:
            logger.warning(f"Could not initialize browser ({e}). Falling back to fixture engine.")
            if self.source_mode == "browser":
                raise
            return False

    def _open_worker_tab(self) -> Optional[PageManager]:
        """Opens a new browser tab in the existing CDP context for parallel use."""
        try:
            if self.browser_mgr and self.browser_mgr.context:
                new_page = self.browser_mgr.context.new_page()
                return PageManager(new_page)
        except Exception as e:
            logger.warning(f"Could not open worker tab: {e}")
        return None

    def _fetch_job_detail(
        self,
        card: Dict[str, Any],
        _tab_index: int = 0,
    ) -> Optional["CollectedJob"]:
        """
        Worker function for ThreadPoolExecutor.
        Each thread creates its OWN Playwright sync context connected via CDP
        to avoid Playwright's greenlet thread-switch restriction.
        """
        from playwright.sync_api import sync_playwright
        from collector.models.schema import CollectedJob
        jurl = card.get("job_url", "")
        try:
            with sync_playwright() as pw:
                browser = pw.chromium.connect_over_cdp(
                    self.browser_mgr.cdp_url, timeout=10000
                )
                ctx = browser.contexts[0] if browser.contexts else browser.new_context()
                page = ctx.new_page()
                pm = PageManager(page)
                try:
                    pm.navigate_to(jurl)
                    self.browser_mgr.check_security_restrictions(page)
                    pm.expand_description()
                    pm.expand_history_pagination()
                    pm.scroll_to_bottom()
                    pm.expand_all_reviews()
                    detail_html = page.content()
                    job_obj = parse_job_detail_page(detail_html, job_url=jurl, search_card_metadata=card)
                    safe_id = (job_obj.job_id or jurl).replace("~", "").replace("/", "_").replace(":", "_")[:80]
                    job_obj.links = {
                        "job_post_url": job_obj.job_url,
                        "client_profile_url": f"https://www.upwork.com/companies/~{job_obj.job_id.lstrip('~')}" if job_obj.job_id else "",
                        "reviews_anchor": job_obj.job_url + "#client-history" if job_obj.job_url else "",
                        "raw_html_file": f"raw_html/{safe_id}.html",
                        "job_id": job_obj.job_id,
                    }
                    pm.polite_delay()
                    return job_obj
                except SecurityRestrictionError:
                    raise
                except Exception as e:
                    logger.error(f"Failed to extract job {jurl}: {e}")
                    error_logger.log_error(jurl, str(e))
                    return None
                finally:
                    try:
                        page.close()
                    except Exception:
                        pass
        except SecurityRestrictionError:
            raise
        except Exception as e:
            logger.error(f"Worker CDP connect error for {jurl}: {e}")
            error_logger.log_error(jurl, str(e))
            return None


    def run_test_3_jobs(self) -> List[CollectedJob]:
        """
        MANDATORY FIRST PHASE (Section 20):
        Processes only 3 jobs and prints the exact required validation report:
        JOB TITLE
        JOB URL
        POSTED DATE
        DESCRIPTION LENGTH
        CLIENT LOCATION
        ABOUT CLIENT LENGTH
        RECENT HISTORY COUNT
        FULL REVIEW COUNT
        """
        print("\n" + "=" * 65)
        print("    UPWORK INTELLIGENCE COLLECTOR: 3-JOB TEST MODE (PHASE 1)")
        print("=" * 65 + "\n")

        start_time = datetime.now(timezone.utc)
        cutoff_dt = get_cutoff_datetime(settings.date_range_months, reference_time=start_time)

        # Determine data source
        use_browser = False
        if self.source_mode != "mock":
            try:
                use_browser = self._init_browser_if_needed()
            except Exception as e:
                logger.warning(f"Browser mode unavailable ({e}). Using high-fidelity test fixtures.")
                use_browser = False

        collected: List[CollectedJob] = []
        search_url = settings.build_search_url(page=1)

        if use_browser and self.page_mgr:
            try:
                cur_url = self.page_mgr.page.url.lower()
                if "upwork.com/nx/search/jobs" not in cur_url:
                    self.page_mgr.navigate_to(search_url)
                else:
                    logger.info(f"Using already open Upwork search tab: {self.page_mgr.page.url}")
                self.browser_mgr.check_security_restrictions(self.page_mgr.page)
                self.page_mgr.polite_delay(2.0)

                html = self.page_mgr.get_content()
                search_cards = parse_search_page_html(html)
                logger.info(f"Discovered {len(search_cards)} jobs on search page 1.")

                # Process jobs until 3 are fully collected
                for card in search_cards:
                    if len(collected) >= 3:
                        break
                    jid = card.get("job_id")
                    jurl = card.get("job_url")
                    logger.info(f"Opening job: {card.get('job_title')} ({jurl})")
                    try:
                        self.page_mgr.navigate_to(jurl)
                        self.browser_mgr.check_security_restrictions(self.page_mgr.page)
                        self.page_mgr.expand_description()
                        self.page_mgr.expand_history_pagination()
                        self.page_mgr.scroll_to_bottom()
                        self.page_mgr.expand_all_reviews()

                        job_html = self.page_mgr.get_content()
                        job = parse_job_detail_page(job_html, job_url=jurl, search_card_metadata=card)
                        collected.append(job)
                    except Exception as e:
                        error_logger.log_error(jurl, str(e))
                        self.page_mgr.capture_debug_snapshot(jurl, "detail_page", str(e))
                        logger.error(f"Error extracting job {jurl}: {e}")

                # Return tab back to manager's search page
                try:
                    self.page_mgr.navigate_to(search_url)
                except Exception:
                    pass
            except SecurityRestrictionError as e:
                logger.error(f"Security restriction encountered: {e}")
                print(f"\n[ALERT] Upwork security challenge or login requested: {e}")
            finally:
                if self.browser_mgr:
                    self.browser_mgr.close()

        # Fallback to high-fidelity catalog fixtures
        if not collected:
            logger.info("Extracting jobs from high-fidelity reference fixture catalog...")
            mock_search_html = generate_mock_search_page_html()
            search_cards = parse_search_page_html(mock_search_html)

            for i, cat in enumerate(MOCK_JOBS_CATALOG[:3]):
                detail_html = generate_mock_job_detail_html(
                    job_id=cat["job_id"],
                    title=cat["title"],
                    location=cat["location"],
                    posted_raw=cat["posted_raw"],
                    budget_raw=cat["budget_raw"],
                    experience=cat["experience"],
                    skills=cat["skills"],
                    description=cat["description"],
                    client_spend=cat["client_spend"],
                    client_rating=cat["client_rating"],
                    history_count=cat["history_count"],
                )
                card_meta = search_cards[i] if i < len(search_cards) else None
                job = parse_job_detail_page(
                    detail_html,
                    job_url=f"https://www.upwork.com/jobs/{cat['job_id']}",
                    search_card_metadata=card_meta,
                )
                collected.append(job)

        # Print Section 20 mandatory output format
        is_live = bool(collected and not collected[0].job_id.startswith("~01dutch20comic001"))
        print("\n" + "-" * 55)
        print("         3-JOB TEST MODE EXTRACTION METRICS")
        print(f"         LIVE_BROWSER_DATA = {'TRUE' if is_live else 'FALSE'}")
        print(f"         MOCK_DATA_USED    = {'FALSE' if is_live else 'TRUE'}")
        print("-" * 55)
        for idx, j in enumerate(collected, 1):
            full_reviews_count = sum(1 for h in j.client_recent_history if h.feedback_full)
            about_client_len = len(j.client.about_client_text)
            desc_len = len(j.job.description)

            print(f"\nJob {idx}")
            print(f"Title:                {j.job_title}")
            print(f"Job URL:              {j.job_url}")
            print(f"Posted Date:          {j.posted_at} ({j.posted_raw})")
            print(f"Description Length:   {desc_len:,} chars")
            print(f"Client Location:      {j.client_location or j.client.location or 'Not displayed'}")
            print(f"About Client Length:  {about_client_len:,} chars")
            print(f"Recent History Count: {len(j.client_recent_history)} items")
            print(f"Full Reviews Count:   {full_reviews_count}")

        print("\n" + "-" * 55)

        # Export test files
        scrape_meta = ScrapeRunMeta(
            started_at=start_time.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            search_url=search_url,
            cutoff_date=cutoff_dt.isoformat(),
            pages_processed=1,
            jobs_discovered=len(collected),
            jobs_processed=len(collected),
        )

        p_json = export_jobs_json(collected, scrape_meta, merge=False)
        p_csv = export_jobs_csv(collected, merge=False)
        p_hist = export_client_history_csv(collected, merge=False)
        p_sum = export_run_summary_json(
            pages_processed=1,
            jobs_discovered=len(collected),
            jobs_processed=len(collected),
            duplicates=0,
            failed_jobs=0,
            date_from=cutoff_dt.strftime("%Y-%m-%d"),
            date_to=start_time.strftime("%Y-%m-%d"),
        )

        print(f"[OK] Section 8  JSON exported: {p_json}")
        print(f"[OK] Section 12 CSV exported:  {p_csv}")
        print(f"[OK] Section 12 Hist exported: {p_hist}")
        print(f"[OK] Section 12 Run Summary:   {p_sum}")
        print("=" * 65 + "\n")

        return collected

    def run_full_collection(
        self,
        resume: bool = False,
        max_pages: Optional[int] = None,
        start_page_override: Optional[int] = None,
        start_location_index_override: Optional[int] = None,
        min_age_days: Optional[float] = None,
        max_age_days: Optional[float] = None,
        combined_locations: bool = True,
        page_step: int = 1,
        keep_browser_open: bool = False,
        location_indices: Optional[List[int]] = None,
    ) -> Tuple[List[CollectedJob], Dict[str, Any]]:
        """
        Executes collection governed by date cutoffs and optional min/max age windows.
        start_page_override: if set, start from this page.
        start_location_index_override: if set, start from this location index.
        min_age_days: if set, skip jobs younger than this (e.g. 6 days ago).
        max_age_days: if set, skip jobs older than this (e.g. 15 days ago) and halt/advance when exceeded.
        """
        start_time = datetime.now(timezone.utc)
        cutoff_dt = get_cutoff_datetime(
            months=settings.date_range_months,
            days=settings.date_range_days,
            reference_time=start_time,
        )
        cutoff_iso = cutoff_dt.isoformat()
        window_desc = f"{settings.date_range_days} days" if settings.date_range_days > 0 else f"{settings.date_range_months} month(s)"
        logger.info(f"Date cutoff window: last {window_desc} -> cutoff at {cutoff_iso}")
        if min_age_days is not None or max_age_days is not None:
            logger.info(f"Target Age Window: {min_age_days or 0} to {max_age_days or 'cutoff'} days ago.")

        start_page = start_page_override or 1
        start_location_index = start_location_index_override if start_location_index_override is not None else 0
        seen_ids: List[str] = []

        if resume and not start_page_override:
            ckpt = self.checkpoint_mgr.load_checkpoint()
            if ckpt:
                start_page = ckpt.last_completed_page + 1
                start_location_index = getattr(ckpt, 'current_location_index', start_location_index)
                seen_ids = ckpt.processed_job_ids
                logger.info(f"Resuming collection from Location {start_location_index}, Page {start_page} with {len(seen_ids)} previously processed jobs.")
        elif start_page_override:
            start_page = start_page_override
            if resume:
                ckpt = self.checkpoint_mgr.load_checkpoint()
                if ckpt:
                    start_page = max(start_page_override, ckpt.last_completed_page + 1)
                    start_location_index = getattr(ckpt, 'current_location_index', start_location_index)
                    seen_ids = ckpt.processed_job_ids
            main_ckpt = settings.output_path / "checkpoint.json"
            if main_ckpt.exists():
                try:
                    import json
                    md = json.loads(main_ckpt.read_text(encoding="utf-8"))
                    seen_ids = list(set(seen_ids + md.get("processed_job_ids", [])))
                except Exception:
                    pass
            logger.info(f"Starting at Page {start_page} (Loc {start_location_index}) with {len(seen_ids)} deduplication IDs.")

        self.db = JobDatabase(existing_job_ids=seen_ids)
        paginator = Paginator(
            cutoff_dt=cutoff_dt,
            min_age_days=min_age_days,
            max_age_days=max_age_days,
        )

        use_browser = False
        if self.source_mode != "mock":
            try:
                use_browser = self._init_browser_if_needed()
            except Exception as e:
                logger.warning(f"Browser unavailable: {e}. Running simulation source.")
                use_browser = False

        failed_jobs = 0
        current_page = start_page
        current_loc_index = start_location_index

        # Determine location mode:
        if location_indices is not None:
            use_combined = False
            if resume and start_location_index in location_indices:
                loc_chunks = [i for i in location_indices if i >= start_location_index]
            else:
                loc_chunks = location_indices
            current_loc_index = loc_chunks[0] if loc_chunks else (location_indices[0] if location_indices else 0)
        else:
            use_combined = combined_locations and start_location_index_override is None
            loc_chunks = [None] if use_combined else list(range(current_loc_index, len(settings.target_locations)))
        search_url_base = settings.build_search_url(page=1, location=None if use_combined else settings.target_locations[current_loc_index])

        try:
            for loc_target in loc_chunks:
                if self.is_stopped:
                    logger.info("Collection stop flag received. Exiting location loop.")
                    break

                if loc_target is None:
                    current_location = None
                    loc_display = "All 25 Locations Combined (US, UK, Europe, Australia, etc.)"
                    loc_idx_val = 0
                else:
                    current_loc_index = loc_target
                    current_location = settings.target_locations[current_loc_index]
                    loc_display = current_location
                    loc_idx_val = current_loc_index

                logger.info(f"=== Starting Search for: {loc_display} ===")

                while True:
                    if self.is_stopped:
                        break
                    security_hit = False  # reset each page iteration

                    while self.is_paused:
                        logger.info("Collection paused. Waiting...")
                        time.sleep(2.0)

                    page_url = settings.build_search_url(page=current_page, location=current_location)
                    logger.info(f"=== Fetching Search Page {current_page} ({page_url}) ===")

                    search_cards: List[Dict[str, Any]] = []

                    if use_browser and self.page_mgr:
                        try:
                            self.page_mgr.navigate_to(page_url)
                            self.browser_mgr.check_security_restrictions(self.page_mgr.page)
                            if "search/jobs" not in self.page_mgr.page.url.lower():
                                self.page_mgr.navigate_to(page_url)
                            # Wait up to 10 seconds for Upwork React job tiles to render
                            for attempt in range(5):
                                time.sleep(1.5)
                                html = self.page_mgr.get_content()
                                search_cards = parse_search_page_html(html)
                                if search_cards:
                                    break
                        except SecurityRestrictionError as e:
                            logger.error(f"Security stop encountered on Page {current_page}: {e}")
                            self.checkpoint_mgr.save_checkpoint(
                                last_completed_page=current_page - 1,
                                processed_job_ids=self.db.get_seen_ids(),
                                cutoff_date=cutoff_iso,
                                last_processed_job=self.db.get_last_job().job_id if self.db.job_count > 0 else "",
                                status="stopped_security_prompt",
                                current_location_index=loc_idx_val,
                            )
                            security_hit = True
                            break
                        except Exception as e:
                            logger.error(f"Error fetching page {current_page}: {e}")
                            error_logger.log_error(page_url, str(e))
                            break
                    else:
                        # Offline / simulation fixtures
                        mock_search_html = generate_mock_search_page_html()
                        search_cards = parse_search_page_html(mock_search_html)

                    # Upwork hard cap check: Upwork limits any search query to 100 pages (5,000 jobs)
                    # When page > 100 is requested, Upwork redirects back to page 1
                    if current_page > 100:
                        logger.info(f"Reached Upwork's search page limit of 100 pages (5,000 jobs) for {loc_display}. Query completed.")
                        should_stop = True
                        break

                    if use_browser and self.page_mgr and current_page > 1:
                        cur_url = self.page_mgr.page.url.lower()
                        if "page=1&" in cur_url or cur_url.endswith("&page=1") or "page=" not in cur_url:
                            logger.info(f"Reached Upwork's search page limit (requested page {current_page}, browser at page 1). Query completed.")
                            should_stop = True
                            break

                    if not search_cards:
                        logger.info(f"No more search cards returned on page {current_page}. Reached end of results.")
                        break

                    for _ in search_cards:
                        self.db.register_discovery()

                    # Dynamic Date Boundary check (Section 9)
                    valid_jobs, should_stop = paginator.evaluate_page_jobs(search_cards, start_time)
                    logger.info(f"Page {current_page}: {len(valid_jobs)}/{len(search_cards)} jobs within 1-month date window.")

                    # --- SEQUENTIAL JOB DETAIL FETCHING (Playwright sync API is greenlet-based, not thread-safe) ---
                    security_hit = False
                    page_collected: List[CollectedJob] = []
                    for card in valid_jobs:
                        if self.is_stopped:
                            break

                        jid = card.get("job_id")
                        jurl = card.get("job_url") or (f"https://www.upwork.com/jobs/{jid}" if jid else "")
                        if not jurl or not jurl.startswith("http"):
                            logger.warning(f"Skipping card with missing or invalid URL: {card.get('job_title')}")
                            continue

                        # Atomically claim the job to prevent other scrapers from processing it simultaneously
                        if not self.db.claim_job(jid or jurl):
                            self.db.duplicates_count += 1
                            logger.info(f"Skipping already claimed/duplicate job: {jid}")
                            continue

                        job_obj: Optional[CollectedJob] = None
                        if use_browser and self.page_mgr:
                            try:
                                self.page_mgr.navigate_to(jurl)
                                self.browser_mgr.check_security_restrictions(self.page_mgr.page)
                                self.page_mgr.expand_description()
                                self.page_mgr.expand_history_pagination()
                                self.page_mgr.scroll_to_bottom()
                                self.page_mgr.expand_all_reviews()
                                detail_html = self.page_mgr.get_content()
                                job_obj = parse_job_detail_page(detail_html, job_url=jurl, search_card_metadata=card)
                                job_obj.raw_html = detail_html
                                safe_id = (job_obj.job_id or jurl).replace("~", "").replace("/", "_").replace(":", "_")[:80]
                                job_obj.links = {
                                    "job_post_url": job_obj.job_url,
                                    "client_profile_url": f"https://www.upwork.com/companies/~{job_obj.job_id.lstrip('~')}" if job_obj.job_id else "",
                                    "reviews_anchor": job_obj.job_url + "#client-history" if job_obj.job_url else "",
                                    "raw_html_file": f"raw_html/{safe_id}.html",
                                    "job_id": job_obj.job_id,
                                }
                                # Save raw HTML immediately to disk
                                try:
                                    raw_dir = settings.output_path / "raw_html"
                                    raw_dir.mkdir(parents=True, exist_ok=True)
                                    (raw_dir / f"{safe_id}.html").write_text(detail_html, encoding="utf-8", errors="replace")
                                except Exception:
                                    pass
                                # Strip raw HTML from memory to keep RAM usage minimal
                                job_obj.raw_html = ""
                                self.page_mgr.polite_delay()
                            except SecurityRestrictionError as e:
                                logger.error(f"Security stop on {jurl}: {e}")
                                security_hit = True
                                break
                            except Exception as e:
                                failed_jobs += 1
                                error_logger.log_error(jurl, str(e))
                                self.page_mgr.capture_debug_snapshot(jurl, "detail_page", str(e))
                                logger.error(f"Failed to extract {jurl}: {e}")
                                continue
                        else:
                            cat = MOCK_JOBS_CATALOG[self.db.job_count % len(MOCK_JOBS_CATALOG)]
                            detail_html = generate_mock_job_detail_html(
                                job_id=cat["job_id"], title=cat["title"], location=cat["location"],
                                posted_raw=cat["posted_raw"], budget_raw=cat["budget_raw"],
                                experience=cat["experience"], skills=cat["skills"],
                                description=cat["description"], client_spend=cat["client_spend"],
                                client_rating=cat["client_rating"], history_count=cat["history_count"],
                            )
                            job_obj = parse_job_detail_page(detail_html, job_url=jurl, search_card_metadata=card)

                        if job_obj:
                            self.db.add_job(job_obj)
                            page_collected.append(job_obj)
                            posted_display = job_obj.posted_at or job_obj.posted_raw or ""
                            logger.info(
                                f"[{self.db.job_count}] Collected: '{job_obj.job_title[:40]}...' "
                                f"| Client: {job_obj.client_location} | History: {len(job_obj.client_recent_history)}"
                                f" | Posted: {posted_display}"
                            )
                            self._append_live_feed(job_obj)

                    if security_hit:
                        self.checkpoint_mgr.save_checkpoint(
                            last_completed_page=current_page - 1,
                            processed_job_ids=self.db.get_seen_ids(),
                            cutoff_date=cutoff_iso,
                            last_processed_job=self.db.get_last_job().job_id if self.db.job_count > 0 else "",
                            status="stopped_security_prompt",
                            current_location_index=loc_idx_val,
                        )
                        break

                    # Save checkpoint after each completed page (Section 11)
                    self.checkpoint_mgr.save_checkpoint(
                        last_completed_page=current_page,
                        processed_job_ids=self.db.get_seen_ids(),
                        cutoff_date=cutoff_iso,
                        last_processed_job=self.db.get_last_job().job_id if self.db.job_count > 0 else "",
                        status="completed" if should_stop else "running",
                        current_location_index=loc_idx_val,
                    )

                    # Intermediate dataset export after each completed page (stream to CSVs directly)
                    if len(page_collected) > 0:
                        try:
                            export_jobs_csv(page_collected, merge=True)
                            export_client_history_csv(page_collected, merge=True)
                            # Only merge heavy JSON every 20 pages to conserve RAM
                            if current_page % 20 == 0:
                                meta = ScrapeRunMeta(
                                    started_at=start_time.isoformat(),
                                    finished_at=datetime.now(timezone.utc).isoformat(),
                                    search_url=search_url_base,
                                    cutoff_date=cutoff_iso,
                                    pages_processed=current_page - start_page + 1,
                                    jobs_discovered=self.db.jobs_discovered,
                                    jobs_processed=self.db.job_count,
                                )
                                export_jobs_json(page_collected, meta, merge=True)
                        except Exception as ex:
                            logger.debug(f"Intermediate dataset sync note: {ex}")

                    import gc
                    gc.collect()

                    if should_stop:
                        logger.info(f"Stopping condition met: Date boundary passed for {loc_display}.")
                        break

                    if max_pages and current_page >= max_pages:
                        logger.info(f"Max page limit ({max_pages}) reached.")
                        break

                    current_page += page_step
                    if use_browser and self.page_mgr:
                        delay = settings.delay_between_pages_seconds if len(valid_jobs) > 0 else 1.0
                        self.page_mgr.polite_delay(delay)

                # --- End of while True (Page loop) ---
                if self.is_stopped or security_hit or (max_pages and current_page >= max_pages):
                    break
                else:
                    if use_combined:
                        # Combined mode covers all 25 locations in a single pass
                        break
                    # Move to next location chunk
                    current_page = 1
                    self.checkpoint_mgr.save_checkpoint(
                        last_completed_page=0,
                        processed_job_ids=self.db.get_seen_ids(),
                        cutoff_date=cutoff_iso,
                        last_processed_job=self.db.get_last_job().job_id if self.db.job_count > 0 else "",
                        status="running",
                        current_location_index=loc_idx_val + 1,
                    )

        finally:
            if not keep_browser_open and self.browser_mgr:
                self.browser_mgr.close()
                self.browser_mgr = None
                self.page_mgr = None

        # Exports
        total_jobs_count = self.db.job_count
        scrape_meta = ScrapeRunMeta(
            started_at=start_time.isoformat(),
            finished_at=datetime.now(timezone.utc).isoformat(),
            search_url=search_url_base,
            cutoff_date=cutoff_iso,
            pages_processed=current_page - start_page + 1,
            jobs_discovered=self.db.jobs_discovered,
            jobs_processed=total_jobs_count,
        )

        p_json = settings.output_path / "jobs.json"
        p_csv = settings.output_path / "jobs.csv"
        p_hist = settings.output_path / "client_history.csv"
        all_jobs = []

        if not keep_browser_open:
            try:
                all_jobs = self.db.get_all_jobs()
                p_json = export_jobs_json(all_jobs, scrape_meta)
                p_csv = export_jobs_csv(all_jobs)
                p_hist = export_client_history_csv(all_jobs)
            except BaseException as ex:
                logger.warning(f"Final in-memory export skipped ({ex}). Streaming CSVs and database on disk are already complete.")
                all_jobs = []

        p_sum = export_run_summary_json(
            pages_processed=current_page - start_page + 1,
            jobs_discovered=self.db.jobs_discovered,
            jobs_processed=total_jobs_count,
            duplicates=self.db.duplicates_count,
            failed_jobs=failed_jobs,
            date_from=cutoff_dt.strftime("%Y-%m-%d"),
            date_to=start_time.strftime("%Y-%m-%d"),
        )

        summary_dict = {
            "pages_processed": current_page - start_page + 1,
            "jobs_discovered": self.db.jobs_discovered,
            "jobs_processed": total_jobs_count,
            "duplicates": self.db.duplicates_count,
            "failed_jobs": failed_jobs,
            "cutoff_date": cutoff_iso,
            "exports": {
                "json": str(p_json),
                "jobs_csv": str(p_csv),
                "client_history_csv": str(p_hist),
                "summary": str(p_sum),
            }
        }
        return all_jobs, summary_dict
