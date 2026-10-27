"""
Deduplication and record repository for Upwork Collector.
Backed by SQLite WAL to support concurrent multi-process scraping.
"""

import sqlite3
import json
from typing import Set, List, Optional
from pathlib import Path
from collector.models.schema import CollectedJob
from collector.storage.central import CentralStore, database_path

class JobDatabase:
    """Manages unique job records and deduplication across pages via SQLite WAL."""

    def __init__(self, db_path: str = None, existing_job_ids: Optional[List[str]] = None):
        self.db_path = str(Path(db_path or database_path()).resolve())
        self.store = CentralStore(self.db_path)
        self.store.initialize()
        # Ensure directory exists
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()
        
        # We maintain in-memory counters for dashboard stats, but the source of truth is SQLite.
        self.duplicates_count: int = 0
        self.jobs_discovered: int = 0
        
        if existing_job_ids:
            with self.get_conn() as conn:
                for jid in existing_job_ids:
                    try:
                        conn.execute("INSERT INTO seen_ids (job_id) VALUES (?)", (jid,))
                    except sqlite3.IntegrityError:
                        pass
                conn.commit()

    def get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self):
        with self.get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS seen_ids (
                    job_id TEXT PRIMARY KEY
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    job_json TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claims (
                    job_id TEXT PRIMARY KEY,
                    claimed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            # Clean up unfulfilled claims from previously interrupted runs
            conn.execute("""
                DELETE FROM claims WHERE job_id NOT IN (SELECT job_id FROM jobs)
            """)
            # Ensure all existing completed jobs are registered in claims and seen_ids
            conn.execute("""
                INSERT OR IGNORE INTO claims (job_id) SELECT job_id FROM jobs
            """)
            conn.execute("""
                INSERT OR IGNORE INTO seen_ids (job_id) SELECT job_id FROM jobs
            """)
            conn.commit()

    def claim_job(self, job_id: str) -> bool:
        """
        Atomically attempts to claim a job. Returns True if claimed successfully, 
        False if another scraper has already claimed it or it already exists in the database.
        """
        with self.get_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
            if c.fetchone():
                return False
            c.execute("SELECT 1 FROM seen_ids WHERE job_id = ?", (job_id,))
            if c.fetchone():
                return False
            try:
                conn.execute("INSERT INTO claims (job_id) VALUES (?)", (job_id,))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    @property
    def seen_ids(self) -> Set[str]:
        # Provide a property that returns a set to be backwards compatible
        with self.get_conn() as conn:
            cursor = conn.execute("SELECT job_id FROM seen_ids")
            return {row[0] for row in cursor.fetchall()}
            
    @property
    def jobs(self) -> List[CollectedJob]:
        # Return list of CollectedJob objects
        return self.get_all_jobs()

    @property
    def job_count(self) -> int:
        with self.get_conn() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM jobs")
            return cursor.fetchone()[0]

    def get_last_job(self) -> Optional[CollectedJob]:
        with self.get_conn() as conn:
            cursor = conn.execute("SELECT job_json FROM jobs ORDER BY rowid DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                return CollectedJob.model_validate_json(row[0])
            return None

    def is_seen(self, job_id: str, job_url: str = "") -> bool:
        """Checks if a job has already been registered."""
        key = job_id or job_url
        with self.get_conn() as conn:
            cursor = conn.execute("SELECT 1 FROM seen_ids WHERE job_id = ?", (key,))
            return cursor.fetchone() is not None

    def register_discovery(self):
        self.jobs_discovered += 1

    def add_job(self, job: CollectedJob) -> bool:
        """Upsert one job row; keep richer saved descriptions and reviews."""
        key = job.job_id or job.job_url
        data = job.model_dump(mode="json")
        raw = data.pop("raw_html", "")
        with self.get_conn() as conn:
            old = conn.execute("SELECT job_json FROM jobs WHERE job_id=?", (key,)).fetchone()
        merged = self.store.save(key, data, raw)
        with self.get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO seen_ids(job_id) VALUES(?)", (key,))
        changed = old is None or json.loads(old[0]) != merged
        if not changed:
            self.duplicates_count += 1
        return changed

    def get_all_jobs(self) -> List[CollectedJob]:
        jobs = []
        with self.get_conn() as conn:
            cursor = conn.execute("SELECT job_json FROM jobs")
            while True:
                rows = cursor.fetchmany(50)
                if not rows:
                    break
                for row in rows:
                    try:
                        jobs.append(CollectedJob.model_validate_json(row[0]))
                    except Exception:
                        pass
        return jobs

    def get_seen_ids(self) -> List[str]:
        with self.get_conn() as conn:
            cursor = conn.execute("SELECT job_id FROM seen_ids")
            return [row[0] for row in cursor.fetchall()]
