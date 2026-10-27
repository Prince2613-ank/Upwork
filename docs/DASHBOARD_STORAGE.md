# Dashboard, cleanup and report files

The dashboard has one primary navbar. Pause/Resume/Stop, Clean, the run status and sign-out icon remain in its top-right corner. Date-window and saved-job search controls are expanded on their respective pages. Running is blue, paused/cooldown is yellow, and access or recovery problems are red. Overview uses the current collection with a fixed 15-minute speed chart.

Browsers includes a Scraper speed form. Choose 1–20 job attempts/minute per worker and click Apply speed. Both workers read the saved value before starting their next detail fetch; no worker restart or pause is required. The default is 6 per worker. The displayed combined target is twice the selected value, while actual throughput also depends on discovery, page loading, history pagination and cooldowns. Changing speed does not clear rate-limit or account-verification pauses.

Workers reuse their authenticated browser connection across jobs and disconnect on pause or run completion. History readiness recognises delayed heading-based cards, including Upwork's h5 headings. Each history page is parsed from its own card; contract content changes determine pagination readiness even when page sizes are equal. Full-page Nuxt data remains available for restoring truncated feedback. The final detail parser skips redundant history parsing because the complete traversal has already supplied that data.

Local API reload is opt-in through `python -m server.launcher --reload`; the default launcher uses stable API mode. Restart services after backend changes, pausing work first so durable queue claims can settle.

On Windows, dedicated browser windows start hidden while retaining their regular browser profiles. Browsers has one Show both browsers / Hide both browsers toggle; changing visibility does not pause scraping or restart the browsers. Manual Take control / Login still requires paused, idle workers. Release control hides both windows and clears the manual-control lock. The old always-visible environment override no longer forces windows open. A dashboard tab does not need to remain open, but local collection requires the laptop to remain awake and online. Server deployments use their isolated virtual browser desktops instead.

## Clean latest collection

This is a database operation, replacing the former display-only clear. The navbar Clean button opens a confirmation dialog; Cancel or Escape makes no changes, and Clean jobs submits the deletion. Stop the active collection first and wait for any in-flight queue claim to finish. The authenticated, CSRF-protected endpoint rejects cleaning while another run is active or a job is being processed.

Cleaning removes the latest run's completed job IDs from the pipeline's canonical job table, clears that run's queued cards and result snapshots, and marks the run `cleaned`. Older unrelated jobs remain. Run metadata and HTML files are retained. A cleaned run cannot be retried or recompiled; start a new date window instead. Previously generated reports can still be downloaded or sent through Files. Raw HTML/diagnostic artifacts have separate retention and are not deleted by this operation.

Cleanup is idempotent: clicking it again does not advance to deleting an older collection. It does not automatically clean existing data when upgrading the application.

## Files

The Files page lists generated HTML reports, including reports with the previous filenames. Local installations using the default `output/server` data directory also list HTML exports directly under `output` and reports under `output/reports`. Browser input never supplies a filesystem path; downloads require an authenticated session.

New reports use `upwork_<weekday>_scrape_<YYYY-MM-DD>.html`, for example `upwork_Tuesday_scrape_2026-10-27.html`. The weekday and date come from the run's start timestamp in its configured timezone; the collected posting window is displayed separately. Each run has a separate folder under `PIPELINE_DATA_DIR/reports/<run-id>/`, so same-day runs do not overwrite one another. Downloads and Google Chat attachments use the same filename.

HTML release is automatic after discovery finishes and all queued jobs reach a terminal state. Only report-qualified jobs are included. The supervisor queues the attachment automatically when the dashboard's Google Chat delivery setting is enabled. Report-generation failures retry up to five times with backoff before requesting attention; collected jobs remain intact. Attachment delivery has its own five-attempt retry budget and never restarts collection. Files shows the Chat delivery state, and successful uploads are recorded in Events. Saved Google OAuth refresh credentials renew expired access tokens during delivery; revoked grants still require a new Google authorization.

Restart the dashboard API after installing these backend changes, then hard-refresh the browser. Stop ongoing work before restarting a combined local launcher, since it supervises worker processes too.
