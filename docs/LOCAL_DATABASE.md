# Permanent local database

The local collectors now use `output/database.db` for every date. They no longer create daily, weekend, today, weekly or fortnightly database copies. `LOCAL_DATABASE_PATH` can override the local path.

Tables:

- `jobs`: one row per Upwork job ID, with indexed `posted_date`, original `first_seen_at`, latest `updated_at`, JSON details and raw HTML. Re-fetching a known ID updates the existing row and preserves richer descriptions/reviews.
- `collection_runs`: one row per collection attempt/window. A new day or changed dashboard window opens another run row.
- `run_jobs`: associates each job with its runs without duplicating its full record.
- `legacy_imports`: remembers which existing files have already been merged.

The dashboard filters rows by posting date before limiting the results. CSV exports and standalone HTML reports read date windows from the permanent database. The default local daily window is yesterday only.

The first collector startup performs an incremental, read-only import from existing `output/database*.db` files. It first creates a one-time backup at `output/backups/database_before_consolidation.db`. Original daily files are retained; deleting them is a separate operator decision after verifying the merge. An interrupted import can be rerun. To import manually:

```powershell
python -m collector.storage.central --directory output
```

Restart any already-running local collector/dashboard once to load this code. Historical files will remain visible on disk but new local saves go only to the permanent database. Do not run an older copy of the scraper that still writes the daily files.

The Linux server pipeline continues to use one PostgreSQL database through `DATABASE_URL`. This local SQLite change does not deploy PostgreSQL or migrate local records into the server; use the server import procedure in `SERVER_DEPLOYMENT.md` for that one-time transfer.

Regression checks:

```powershell
python -m unittest discover -s tests -p test_central_database.py -v
```
