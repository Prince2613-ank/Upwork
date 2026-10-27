# Linux deployment

Docker runs the API, PostgreSQL 18, a scheduler, two scraper workers, two persistent Chromium sessions and Caddy HTTPS. Only ports 80/443 are public. CDP, PostgreSQL and remote desktops stay internal. Do not run the legacy collector against these browser sessions.

## Configuration

Use Linux with Docker Engine and Compose v2, initially 4 vCPU and 8 GB RAM. Point a domain at the server. Chromium requires user namespaces; keep its sandbox enabled.

Prepare the private environment on your laptop:

```sh
python -m deploy.configure --from-local --domain jobs.yourcompany.com
python -m deploy.configure --check
```

This reuses your dashboard scrypt password hash and Google Chat settings, copies the existing OAuth token to `deploy/secrets/google-chat-token.json`, generates a PostgreSQL password if the old value is a placeholder, and removes obsolete configuration fields. It never prints credentials. Review missing-field messages before deploying. Existing configured secrets are retained. Do not regenerate the database password after PostgreSQL has been initialized: changing the env alone does not rotate the database user's password.

The real `.env.server` and `deploy/secrets` are ignored by Git. Transfer them separately over SSH. Set server permissions:

```sh
chmod 600 .env.server
sudo chown -R 10001:10001 deploy/secrets
sudo chmod 700 deploy/secrets
sudo chmod 600 deploy/secrets/google-chat-token.json
```

To set a different dashboard password interactively, use `python -m server.admin set-password --env-file .env.server`. The supported field is `DASHBOARD_PASSWORD_SCRYPT`; the old Caddy `DASHBOARD_PASSWORD_HASH` is unused.

Local startup reads `.env.local` only. Compose injects `.env.server`, forces `DATABASE_URL=postgresql+psycopg://...@db:5432/flodata`, sets `/data` storage and Linux browser addresses, and disables dotenv file loading. Local paths and SQLite defaults do not leak into containers. To run a host command with server settings explicitly, set `PIPELINE_ENV_FILE=.env.server`; Compose is the recommended server entrypoint.

## Move existing dashboard data

Changing `DATABASE_URL` does not copy SQLite data. The modern dashboard uses `pipeline_*` tables in `output/database.db`. The old `server.admin import-sqlite` command handles legacy `jobs` tables only; do not use it for this migration.

1. Stop collection from the dashboard and wait for both workers to show Waiting. Stop the local launcher after it is idle, so files and database remain aligned during copying. Keep the original local data as a backup.
2. Export the modern pipeline on the laptop:

```sh
python -m server.transfer export --source output/database.db --output output/migration/pipeline.json
```

The export uses SQLite's consistent backup API, including committed WAL data. It copies jobs, history, queue, events, schedule configuration and release records. Dashboard sessions, login limits and worker heartbeats are omitted. No source rows are changed.

3. Copy `output/migration/pipeline.json` and the contents of `output/server` to a private migration directory on Linux, with this structure:

```text
migration/
  pipeline.json
  data/
    raw/
    reports/
    diagnostics/
```

Preserve the report subdirectories and filenames exactly. If you also have old HTML files directly in `output`, copy those into `migration/data/reports/legacy/` so the Files page can list them. Windows browser profiles are not part of this migration; log into each Linux browser once.

4. Build the server image and start PostgreSQL only:

```sh
docker compose --env-file .env.server -f compose.server.yml config --quiet
docker compose --env-file .env.server -f compose.server.yml build
docker compose --env-file .env.server -f compose.server.yml up -d db
```

5. Import into the fresh server database before starting the API, scheduler or workers:

```sh
docker compose --env-file .env.server -f compose.server.yml run --rm -v "$PWD/migration:/imports:ro" api python -m server.transfer import --input /imports/pipeline.json
```

The importer refuses a populated destination, imports in a transaction, checks row counts and resets PostgreSQL integer sequences. Re-importing cannot silently overwrite server work. Running claims become pending, active runs become paused, manual-control locks are cleared, and daily scheduling and Chat delivery are disabled until you verify the server. Old pending alerts are cancelled to prevent stale notifications. Configured dates/timezone and report paths are preserved.

6. Copy the matching data files into the persistent volume:

```sh
docker compose --env-file .env.server -f compose.server.yml run --rm --user 0 -v "$PWD/migration/data:/imports:ro" api sh -c 'cp -a /imports/. /data/ && chown -R 10001:10001 /data'
```

7. Start and verify all services:

```sh
docker compose --env-file .env.server -f compose.server.yml up -d --wait
docker compose --env-file .env.server -f compose.server.yml logs --tail=100
```

Open the HTTPS dashboard, compare saved-job counts and samples with the laptop, and download a migrated HTML file from Files. On Browsers, take control and log into A and B; complete verification manually, then release control. Resume the paused collection. Enable the desired schedule and Chat delivery only after checking the date window, timezone and destination.

For a fresh installation, skip the migration and file-copy steps and start with `up -d --build --wait`.

## Storage and behavior

`postgres18-data` contains the shared database. Each collection is a row; jobs are keyed by job ID, and queue rows preserve membership and snapshots for each collection. There are no new daily database files. `pipeline-data` stores raw HTML, reports and diagnostics. Browser login profiles have separate persistent volumes. PostgreSQL 18 mounts its volume at `/var/lib/postgresql` (data lives under `18/docker`). Do not attach a PostgreSQL 17 data volume to an 18 image; that upgrade requires dump/restore. Ordinary restarts preserve all these volumes. `docker compose down -v` deletes them.

The initial schema is version 2. Future column changes need a versioned migration; SQLAlchemy `create_all` does not alter existing tables. SQLite and PostgreSQL use the same SQLAlchemy schema and dashboard code. PostgreSQL uses row locking and skip-locked queue claims for concurrency.

Speed is adjustable from 1 to 20 detail attempts/minute per worker. Actual completions depend on page and review-history loading. Rate limits respect Retry-After; account restrictions and verification pause work. Neither faster settings nor saved login sessions guarantee uninterrupted access. Remote browser control requires paused, idle workers. Do not scale beyond one supervisor and one scheduler.

A fresh database uses `PIPELINE_TIMEZONE` for its initial schedule timezone. Imported databases retain the user's stored schedule timezone. The scheduler handles yesterday or the configured completed-date window, creates at most one scheduled run per local day, and catches up after restart that day. Missed historical days need an explicit date-window collection.

## Google Chat

Issue messages use `GOOGLE_CHAT_WEBHOOK`; HTML attachments use `GOOGLE_CHAT_SPACE` and `/secrets/google-chat-token.json`. Enable delivery in Schedule after confirming both browser logins. Report names use the collection start timestamp in its timezone: `upwork_Tuesday_scarpe_2026-10-27.html`. Daily releases are automatic when discovery and queued work finish; empty descriptions and jobs without written freelancer reviews are excluded.

To authorize a replacement token on the laptop:

```sh
python -m server.admin google-login --client path/to/client.json --output path/to/google-chat-token.json
```

Copy it into `deploy/secrets` and restore UID 10001 ownership. Existing authorization may be reused if the token remains valid and your Workspace permits the Chat app. Delivery failures retain the downloadable HTML and recorded error; attachment retries are separate from scraping.

## Backups and updates

Run `BACKUP_DIR=/encrypted/off-server-backups sh deploy/backup.sh` on a host timer. Back up `pipeline-data` too. Back up browser profiles while their containers are stopped; they contain login credentials. Test restoring dumps into a disposable database. Never restore over active production work.

GitHub CI tests SQLite and PostgreSQL, validates Compose, and builds the image. The release workflow publishes a commit-SHA image to GHCR. Configure deployment host/user/path and backup variables plus SSH key and verified known-host secrets in GitHub's production environment. Keep credentials out of Git.

Use `FLODATA_IMAGE=ghcr.io/owner/repo:COMMIT_SHA` for a tested release. `deploy/update.sh` pauses work, waits for workers, backs up PostgreSQL and updates containers. Verify health and resume from the dashboard afterward. Linux login, TLS and real Chat delivery still require checks on the actual server.

## Verification

Install `requirements-server.lock` to match the image and CI. Run the deployment tests with `TEST_POSTGRES_URL` pointing at a disposable database:

```sh
python -m pytest tests/test_server_pipeline.py tests/test_production_flow.py tests/test_deployment_transfer.py tests/test_auto_release.py tests/test_files_cleanup.py tests/test_worker_speed.py tests/test_daily_context.py -q
```

Tests use temporary data and do not log into Upwork or send real Chat messages. Keep database credentials out of copied logs and command history.
