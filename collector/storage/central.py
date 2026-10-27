"""One permanent local database. Dates and collection runs are rows, not files."""
import argparse
import copy
import json
import os
import sqlite3
import uuid
from contextlib import contextmanager, closing
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def database_path(output=None):
    return Path(os.getenv("LOCAL_DATABASE_PATH") or ((Path(output) if output else ROOT / "output") / "database.db"))


def merge_data(old, new):
    """Fresh metadata, but never discard richer descriptions or contract history."""
    merged = copy.deepcopy(old)
    for key, value in new.items():
        if value in (None, "", [], {}):
            continue
        previous = merged.get(key)
        if isinstance(previous, dict) and isinstance(value, dict):
            merged[key] = merge_data(previous, value)
        elif key in ("description", "feedback", "feedback_full", "full_review") and isinstance(previous, str) and isinstance(value, str):
            merged[key] = max((previous, value), key=len)
        elif key == "client_recent_history" and isinstance(value, list):
            history = {}
            for item in (previous or []) + value:
                identity = tuple(str(item.get(k) or "") for k in ("job_title", "date", "freelancer_name", "amount"))
                history[identity] = merge_data(history.get(identity, {}), item)
            merged[key] = list(history.values())
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def quality(data):
    return len((data.get("job") or {}).get("description") or data.get("description") or "") + sum(
        len(r.get("feedback") or r.get("full_review") or "") for r in data.get("client_recent_history", []))


class CentralStore:
    def __init__(self, path=None):
        self.path = Path(path) if path is not None else database_path()

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def initialize(self):
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("CREATE TABLE IF NOT EXISTS jobs(job_id TEXT PRIMARY KEY, job_json TEXT, raw_html TEXT, saved_at TEXT DEFAULT (datetime('now')))")
            columns = {r[1] for r in c.execute("PRAGMA table_info(jobs)")}
            for name, declaration in (("raw_html", "TEXT"), ("saved_at", "TEXT"), ("posted_date", "TEXT"),
                                      ("first_seen_at", "TEXT"), ("updated_at", "TEXT")):
                if name not in columns:
                    c.execute(f"ALTER TABLE jobs ADD COLUMN {name} {declaration}")
            c.execute("UPDATE jobs SET posted_date=substr(json_extract(job_json, '$.posted_at'),1,10) WHERE posted_date IS NULL AND json_valid(job_json)")
            c.execute("UPDATE jobs SET first_seen_at=COALESCE(first_seen_at,saved_at,datetime('now')), updated_at=COALESCE(updated_at,saved_at,datetime('now')) WHERE first_seen_at IS NULL OR updated_at IS NULL")
            c.execute("CREATE INDEX IF NOT EXISTS jobs_posted_date_idx ON jobs(posted_date)")
            c.execute("CREATE TABLE IF NOT EXISTS collection_runs(run_id TEXT PRIMARY KEY, start_date TEXT, end_date TEXT, started_at TEXT DEFAULT (datetime('now')), finished_at TEXT, status TEXT)")
            c.execute("CREATE TABLE IF NOT EXISTS run_jobs(run_id TEXT REFERENCES collection_runs(run_id), job_id TEXT REFERENCES jobs(job_id), PRIMARY KEY(run_id,job_id))")
            c.execute("CREATE TABLE IF NOT EXISTS legacy_imports(source TEXT PRIMARY KEY, fingerprint TEXT, imported_at TEXT DEFAULT (datetime('now')))")

    def start_run(self, start, end):
        rid = uuid.uuid4().hex
        with self.connect() as c:
            c.execute("INSERT INTO collection_runs(run_id,start_date,end_date,status) VALUES(?,?,?,'running')", (rid, start, end))
        return rid

    def finish_run(self, rid, status="completed"):
        if rid:
            with self.connect() as c:
                c.execute("UPDATE collection_runs SET status=?,finished_at=datetime('now') WHERE run_id=?", (status, rid))

    def save(self, jid, data, raw="", run_id=None):
        if not jid or not isinstance(data, dict):
            raise ValueError("A job ID and job object are required")
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("SELECT job_json,raw_html FROM jobs WHERE job_id=?", (jid,)).fetchone()
            old = json.loads(row[0]) if row else {}
            merged = merge_data(old, data)
            keep_raw = raw if raw and (not row or not row[1] or quality(data) >= quality(old)) else (row[1] if row else "")
            date = str(merged.get("posted_at") or "")[:10]
            c.execute("""INSERT INTO jobs(job_id,job_json,raw_html,posted_date,first_seen_at,updated_at)
                VALUES(?,?,?,?,datetime('now'),datetime('now'))
                ON CONFLICT(job_id) DO UPDATE SET job_json=excluded.job_json,raw_html=excluded.raw_html,
                posted_date=excluded.posted_date,updated_at=excluded.updated_at""",
                (jid, json.dumps(merged, ensure_ascii=False, default=str), keep_raw, date))
            if run_id:
                c.execute("INSERT OR IGNORE INTO run_jobs(run_id,job_id) VALUES(?,?)", (run_id, jid))
        return merged

    def ids(self, start=None, end=None):
        where, params = date_clause(start, end)
        with self.connect() as c:
            return {r[0] for r in c.execute("SELECT job_id FROM jobs" + where, params)}

    def migrate_legacy(self, directory):
        """Read-only legacy sources, incremental imports, one pre-import backup."""
        directory = Path(directory)
        sources = sorted(directory.glob("database*.db"))
        sources = [p for p in sources if p.resolve() != self.path.resolve()]
        if not sources:
            return {"sources": 0, "rows": 0}
        backup = directory / "backups" / "database_before_consolidation.db"
        if not backup.exists():
            backup.parent.mkdir(parents=True, exist_ok=True)
            with self.connect() as source, closing(sqlite3.connect(backup)) as target:
                source.backup(target)
        imported, count = 0, 0
        for path in sources:
            stat = path.stat()
            fingerprint = f"{stat.st_mtime_ns}:{stat.st_size}"
            wal = Path(str(path) + "-wal")
            if wal.exists():
                w = wal.stat()
                fingerprint += f":{w.st_mtime_ns}:{w.st_size}"
            with self.connect() as c:
                previous = c.execute("SELECT fingerprint FROM legacy_imports WHERE source=?", (str(path.resolve()),)).fetchone()
            if previous and previous[0] == fingerprint:
                continue
            source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
            try:
                columns = {r[1] for r in source.execute("PRAGMA table_info(jobs)")}
                if not {"job_id", "job_json"} <= columns:
                    continue
                raw_column = "raw_html" if "raw_html" in columns else "''"
                for jid, payload, raw in source.execute(f"SELECT job_id,job_json,{raw_column} FROM jobs"):
                    self.save(jid, json.loads(payload), raw or "")
                    count += 1
                with self.connect() as c:
                    c.execute("INSERT INTO legacy_imports(source,fingerprint) VALUES(?,?) ON CONFLICT(source) DO UPDATE SET fingerprint=excluded.fingerprint,imported_at=datetime('now')", (str(path.resolve()), fingerprint))
                imported += 1
            finally:
                source.close()
        return {"sources": imported, "rows": count}


def date_clause(start=None, end=None, column="posted_date"):
    clauses, params = [], []
    if start:
        clauses.append(f"{column} >= ?")
        params.append(start)
    if end:
        clauses.append(f"{column} <= ?")
        params.append(end)
    return (" WHERE " + " AND ".join(clauses) if clauses else ""), params


def iter_job_rows(path, start=None, end=None, include_raw=False):
    """Filter before reading, and stream raw HTML instead of loading all days in RAM."""
    conn = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=ro", uri=True, timeout=30)
    try:
        columns = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
        date_column = "posted_date" if "posted_date" in columns else "substr(CASE WHEN json_valid(job_json) THEN json_extract(job_json,'$.posted_at') END,1,10)"
        where, params = date_clause(start, end, date_column)
        fields = "job_id,job_json"
        if include_raw:
            fields += ",raw_html" if "raw_html" in columns else ",NULL"
        yield from conn.execute("SELECT " + fields + " FROM jobs" + where + " ORDER BY rowid DESC", params)
    finally:
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=ROOT / "output")
    args = parser.parse_args()
    store = CentralStore(database_path(args.directory))
    store.initialize()
    print(json.dumps(store.migrate_legacy(args.directory)))
