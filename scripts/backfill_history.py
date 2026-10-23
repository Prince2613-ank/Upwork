"""
Backfill: re-visits every already-collected job whose Client Recent History
was captured before the pagination fix (View More + Jobs-in-progress toggle)
went live, and replaces its client/history data with the complete version.

Runs in its own dedicated browser tab over the same CDP connection so it does
not interfere with the live forward-collection run happening in parallel.
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collector.config.settings import settings
from collector.browser.browser_manager import BrowserManager
from collector.browser.page_manager import PageManager
from collector.extraction.job_parser import parse_job_detail_page
from collector.storage.csv_export import export_jobs_csv, export_client_history_csv
from collector.models.schema import CollectedJob
from collector.logging.logger import logger

# Timestamp the "Jobs in progress" toggle fix went live (local machine time).
# Any job whose raw_html file predates this may have an incomplete history.
CUTOFF_TS = datetime(2026, 9, 21, 10, 45, 15).timestamp()

JOBS_FILE = settings.output_path / "jobs.json"
RAW_HTML_DIR = settings.output_path / "raw_html"
SAVE_EVERY = 15


def needs_backfill(job: dict) -> bool:
    jid = (job.get("job_id") or "").lstrip("~")
    html_path = RAW_HTML_DIR / f"{jid}.html"
    if html_path.exists() and html_path.stat().st_mtime >= CUTOFF_TS:
        return False
    return True


def save(data: dict):
    JOBS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main():
    data = json.loads(JOBS_FILE.read_text(encoding="utf-8"))
    jobs = data.get("jobs", [])
    by_id = {(j.get("job_id") or "").lstrip("~"): j for j in jobs}
    targets = [j for j in jobs if needs_backfill(j)]
    logger.info(f"Backfill: {len(targets)}/{len(jobs)} jobs need re-fetch for full Client History.")

    browser_mgr = BrowserManager(new_tab=True)
    page = browser_mgr.start()
    pm = PageManager(page)

    done = 0
    failed = 0
    for job in targets:
        jurl = job.get("job_url") or job.get("links", {}).get("job_post_url", "")
        if not jurl:
            continue
        try:
            pm.navigate_to(jurl)
            pm.expand_description()
            pm.expand_history_pagination()
            pm.scroll_to_bottom()
            pm.expand_all_reviews()
            html = pm.get_content()
            updated = parse_job_detail_page(html, job_url=jurl)

            jid = (updated.job_id or job.get("job_id") or "").lstrip("~")
            if jid in by_id:
                by_id[jid]["client_recent_history"] = [h.model_dump() for h in updated.client_recent_history]
                by_id[jid]["client"] = updated.client.model_dump()

            # Touch the raw_html file's mtime so a re-run doesn't redo this job.
            html_path = RAW_HTML_DIR / f"{jid}.html"
            if html_path.exists():
                html_path.write_text(html, encoding="utf-8", errors="replace")

            done += 1
            logger.info(f"[Backfill {done}/{len(targets)}] {jid}: history -> {len(updated.client_recent_history)} items")

            if done % SAVE_EVERY == 0:
                save(data)

            pm.polite_delay()
        except Exception as e:
            failed += 1
            logger.error(f"Backfill failed for {jurl}: {e}")
            continue

    save(data)

    all_jobs = [CollectedJob(**j) for j in jobs]
    export_jobs_csv(all_jobs, merge=False)
    export_client_history_csv(all_jobs, merge=False)

    logger.info(f"Backfill complete: {done} updated, {failed} failed, out of {len(targets)} targeted.")


if __name__ == "__main__":
    main()
