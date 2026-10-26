# Flodata Linux server pipeline

The server entrypoint is `server.app:app`. The legacy `npm start` command and local databases remain available. Do not run the legacy collector and server collector against the same browser profile concurrently.

## Architecture

Docker Compose runs FastAPI, PostgreSQL, one scheduler, one supervisor containing two workers, two isolated Chromium virtual desktops, and Caddy. Browser A and B are reachable internally through their CDP services; the worker names correspond to legacy ports 9222 and 9223. No CDP, VNC, or database ports are published publicly. Only Caddy publishes public ports 80/443. The API additionally binds to host loopback 8000 for diagnostics.

Each worker caps detail attempts at 5–7/minute (default 6). Search navigation has a separate minimum delay. This is not a guarantee of completed throughput or an approved Upwork traffic limit. Account-wide restrictions pause the run. Access challenges are never solved automatically. Complete historical discovery depends on Upwork exposing the relevant postings.

## First installation

1. Provide Ubuntu/Debian Linux, Docker Engine with Compose v2, a domain pointed at the server, and initially 4 vCPU / 8 GB RAM. Verify Chromium's user-namespace sandbox is permitted by the host kernel. Containers use a non-root user and Playwright's seccomp profile; do not add `--no-sandbox` to work around a host restriction.
2. Clone this repository and copy `.env.server.example` to `.env.server`. Use `chmod 600 .env.server`. Set a random hex `POSTGRES_PASSWORD`, a unique dashboard password of at least 16 characters, your domain/public URL, and your Google Chat webhook and space. Keep the webhook private. Schedule and outbound delivery are disabled initially.
3. Generate the Caddy hash interactively: `docker run --rm -it caddy:2 caddy hash-password`. Put the hash of the SAME dashboard password into `DASHBOARD_PASSWORD_HASH`, wrapped in single quotes so Compose does not interpolate dollar signs.
4. `mkdir -p deploy/secrets && sudo chown 10001:10001 deploy/secrets && chmod 700 deploy/secrets`. The application runs as UID 10001. OAuth tokens are refreshed in this writable directory.
5. Leave `UPWORK_SEARCH_URL` blank to preserve the existing collector's 25-location, payment-verified filter, or supply a custom search URL. Recency sorting and page size are enforced by the browser adapter.
6. Run `docker compose --env-file .env.server -f compose.server.yml up -d --build`. Check `docker compose --env-file .env.server -f compose.server.yml logs --tail=100`.
7. Open the HTTPS dashboard. Before launching any collection, open browser A and browser B separately, log in manually, and complete any verification. Persistent profiles remain in separate named volumes. First login may be needed in BOTH profiles. Session validity is checked on navigation; reuse is not a promise of permanent login.
8. Authorise Google Chat as below, then enable delivery and save the desired daily time/timezone. Default schedule is DISABLED, 07:00 Asia/Kolkata, yesterday only. Validate one small date window before a full daily run.

Protect remote browser access as account access. The proxy checks dashboard authentication and refuses remote access while workers are active. Pause and wait for both workers to show Waiting, then open the remote view. Opening it holds a persisted remote-control lock. Click Release remote control to disconnect noVNC sessions and release the lock before Resume. Browser restart requests preserve profiles. Never expose ports 9222/9223/5900/6080/7070 to the internet.

## Google Chat HTML attachment delivery

Incoming webhooks send issue/completion messages, not binary attachments. HTML attachments use the Google Chat `media.upload` and message-create API with user OAuth and the `chat.messages` scope (read checks make retries idempotent). Your Workspace administrator must permit the app, webhook and destination space. File size is capped at 200 MB; Workspace file/security policies can still reject an attachment. Failure leaves a downloadable report and a recorded delivery error.

Create a Google Cloud project, enable the Chat API, configure its app and OAuth consent, and download Desktop OAuth client credentials. On your LOCAL computer, install `requirements-server.txt`, then run:

```powershell
python -m server.admin google-login --client path/to/client.json --output path/to/google-chat-token.json
```

Complete the consent in your local browser as a member of the target space. Securely copy the resulting token to `deploy/secrets/google-chat-token.json` on the server, owned by UID 10001 and mode 600. Set `GOOGLE_CHAT_SPACE=spaces/...`. Do not commit either credential file. External OAuth apps in testing can have short-lived refresh grants; configure production/internal consent as your organisation permits.

The dashboard shows whether webhook and token files are configured. Enable delivery explicitly, run a small collection, and verify both alert and attachment delivery. API delivery retries up to five times, separately from scraping. Alerts also use a persisted outbox with bounded retries; webhook timeouts can occasionally produce duplicate alerts because webhooks do not provide the report API's idempotent message ID. A deterministic message ID prevents duplicate report messages after retries. The operator can retry report delivery from the dashboard.

## Data and migration

`postgres-data` stores all job dates centrally. `pipeline-data` stores compressed, content-addressed raw HTML, screenshots and HTML/CSV/JSON reports. `browser-a-data` and `browser-b-data` store login profiles. These volumes survive ordinary container replacements; NEVER use `docker compose down -v` unless intentionally deleting this data.

The initial SQLAlchemy schema is version 1 and is created when the API starts. Future schema changes require an explicit migration; `create_all` does not upgrade existing tables. Migrate copies of existing SQLite files read-only:

```sh
docker compose --env-file .env.server -f compose.server.yml run --rm -v /absolute/path/to/old/output:/imports:ro api python -m server.admin import-sqlite /imports/database.db /imports/database_today.db
```

Choose all relevant source files. Conflicting imported records are selected by description/review text length, with the source filename recorded. This is a reconciliation heuristic: compare imported counts and sample results before retiring legacy files. Original files are not modified. Import legacy data BEFORE enabling the new worker; importing over fresh production records requires manual review.

## Pipeline behaviour

The scheduler persists the chosen timezone, daily time and window in PostgreSQL. It creates at most one scheduled run per local calendar day after the chosen time. Restarting later that day catches up; this initial version does not automatically backfill every missed historical day. If another run is active, scheduling waits. The supervisor holds a PostgreSQL advisory lock and resets unfinished queue claims after restart. Do not scale the supervisor or scheduler beyond one instance.

Worker A discovers newest-first search pages, and both workers consume unique durable queue entries. The pipeline scans a one-day margin for coarse relative labels, filters detail timestamps in the run timezone, and stops after a fully older search page. Relative timestamps are approximations and are labelled accordingly. Empty/missing date or selector failures pause instead of claiming complete coverage. A safety cap prevents infinite pagination. History expansion is bounded and incomplete/truncated history is flagged in reports; API/DOM changes may require parser updates.

Pause/stop is cooperative: an in-flight bounded browser action can finish before workers become idle. Stop preserves work; Retry can resume failed items. Completed reports are snapshots. Report strings are escaped, and CSV formula-leading cells are neutralised. Remote control must not run concurrently with collection.

Rate limits respect Retry-After and pause both workers. Login/verification errors require manual action. A stalled worker causes the supervisor container to exit for restart; deliberate paused/cooldown states do not cause restart loops. Notifications from the server cannot detect total server/network failure: configure an independent uptime monitor and a missed-daily-report alert externally.

## Backups and restore

Run `BACKUP_DIR=/your/encrypted/backup/path sh deploy/backup.sh` on a host timer. This creates a PostgreSQL custom-format dump. Copy backups OFF the server. Also back up `pipeline-data`; browser profiles contain credentials and need encrypted backups made while their browser containers are stopped. Configure retention on backup storage and periodic pruning of old diagnostic/raw artifacts according to your organisation's needs; this version does not auto-delete collected data.

Test restoring a dump into a disposable PostgreSQL database using `pg_restore --no-owner --no-privileges -U flodata -d RESTORE_DATABASE BACKUP.dump`. Verify row counts and sample exports. Do not restore over the running production database.

## GitHub pipeline and deployment

`server-ci.yml` tests the durable pipeline against SQLite and PostgreSQL, validates Compose, and builds the image on pushes/PRs. `server-release.yml` is manually triggered and publishes a commit-SHA image tag to GHCR. The initial release still requires the Linux browser/login/Chat smoke checks on the target server; unit tests cannot prove access to your account.

Use a tested immutable image tag in `.env.server` (`FLODATA_IMAGE=ghcr.io/owner/repo:COMMIT_SHA`). Authenticate the server to GHCR if the package is private. `deploy/update.sh` pauses work, waits for idle workers, creates a database backup, changes the image tag, pulls and applies services, and waits for health. Verify browser login and resume from the dashboard. Roll back the image tag only if its database schema remains compatible.

For controlled deployment from GitHub, configure a `production` environment with variables `DEPLOY_HOST`, `DEPLOY_USER`, `DEPLOY_PATH`, `BACKUP_DIR`, and secrets `DEPLOY_SSH_KEY` and `DEPLOY_KNOWN_HOSTS` (verified SSH host keys, not blindly scanned during deployment). Configure required reviewers there if your organisation requires them. Install the tracked deployment scripts on the host first. Manually run `Deploy server release` with a full commit SHA already published by the release workflow. This workflow remains inactive until the real server details and credentials are configured. No server login or credentials are committed.

## Local verification

Use a virtual environment and `pip install -r requirements-server.txt`. Run `python -m pytest tests/test_server_pipeline.py -q`. Set `TEST_POSTGRES_URL` to a DISPOSABLE PostgreSQL database to exercise database concurrency. Tests never log into Upwork or send Google Chat messages.

The browser seccomp profile is sourced from https://github.com/microsoft/playwright/blob/main/utils/docker/seccomp_profile.json. Refresh it only alongside a reviewed browser/runtime update.
