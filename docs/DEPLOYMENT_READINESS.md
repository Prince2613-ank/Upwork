# Deployment readiness — 27 October 2026

Seven items verified locally; three require the target server. Local development remains on SQLite. Production uses PostgreSQL 18.

| Item | Status | Evidence / remaining work |
| --- | --- | --- |
| Database compatibility | Verified | The deployment regression suite passed against SQLite and PostgreSQL 18: 122 tests. |
| Environment variables | Pending target values | Private credentials are prepared; the actual domain/public HTTPS URL is still required. Run `python -m deploy.configure --check`. |
| Dependencies | Verified | psycopg and psycopg-binary are pinned in `requirements-server.lock`; the Linux image builds successfully. |
| Database schema | Verified | Shared SQLAlchemy schema, unique constraints, JSON queries, queue claims and imported ID sequences pass PostgreSQL tests. Schema version 2 is recorded; future column changes still require explicit migrations. |
| Data migration | Verified tooling | `server.transfer` copies modern pipeline tables into a fresh PostgreSQL database and verifies row counts. The real data copy and matching report/raw-file copy happen during deployment. |
| Docker configuration | Partially verified | Compose validates; the built Linux API image passes login, health and authenticated status checks on PostgreSQL 18. Full browser, scheduler, proxy and TLS startup still needs the target Linux host. |
| Persistent storage | Verified | An isolated PostgreSQL 18 named volume retained the job payload across container restart. Compose mounts PostgreSQL 18 at `/var/lib/postgresql` and retains application/browser volumes. |
| Backup and recovery | Verified locally | A real `pg_dump -Fc` backup restored with `pg_restore --exit-on-error` into a separate database. Job JSON and table counts matched. The actual server still needs an off-server backup destination, schedule and restore drill. |
| Security | Partially verified | Secrets are Git-ignored; dashboard uses a scrypt hash; Compose does not publish database/CDP/VNC ports and only binds API diagnostics to loopback. Target HTTPS, firewall, SSH access and secret-file permissions remain to be checked. |
| PostgreSQL CRUD | Verified | Create, read, update and delete passed through the actual application schema, including a release-quality JSON query. |

The persistence/restore drill used synthetic data in its own temporary container and volume, both removed afterward. Evidence is in ignored `output/deployment-readiness-verification/result.json`; the retained dump contains synthetic test data only. Existing `my-postgres`, its `mydb` database and local SQLite records were not modified by this drill.

This is deployment preparation, not confirmation that the real server is live. Follow `SERVER_DEPLOYMENT.md`, verify both Linux browser logins, download a report and test real Google Chat delivery before enabling unattended daily scheduling. Local browser profiles and dashboard sessions are not migrated automatically.

## Real-data migration trial

A consistent snapshot of the actual local SQLite database was imported into a separate PostgreSQL 18 database on 27 October 2026. All eight transferred tables matched by row count and content, including 1,809 saved jobs, 6,023 queue rows, two collection runs and 1,893 events. JSON comparison treats numerically equivalent `0` and `0.0` as equal, matching PostgreSQL Float storage.

Dashboard login and the health/status/jobs/analytics/files endpoints passed against the imported database. New event and queue IDs continued correctly after import. All 1,809 referenced raw HTML files exist locally; this snapshot had no completed report paths on its run records. Files still need a separate copy to the server during deployment.

The temporary PostgreSQL database was removed afterward. Local SQLite was neither replaced nor paused. This proves a real-data trial import; it does not mean the real production server has been populated. Detailed evidence: ignored `output/real-data-migration-test/f1fe3b82b1/result.json`. The private SQLite snapshot remains alongside it for this trial.
