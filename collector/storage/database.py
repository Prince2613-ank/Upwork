"""
Deduplication and record repository for Upwork Collector.
Backed by SQLite WAL to support concurrent multi-process scraping.
"""

import sqlite3
import json
from typing import Set, List, Optional
from pathlib import Path
from collector.models.schema import CollectedJob

class JobDatabase:
    """Manages unique job records and deduplication across pages via SQLite WAL."""

    def __init__(self, db_path: str = "./output/database.db", existing_job_ids: Optional[List[str]] = None):
        self.db_path = str(Path(db_path).resolve())
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
        """
        Adds a job if unique. If already seen, updates the record if the new job contains richer details.
        """
        key = job.job_id or job.job_url
        with self.get_conn() as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                cursor = conn.execute("SELECT job_json FROM jobs WHERE job_id = ?", (key,))
                existing_row = cursor.fetchone()
                job_json = job.model_dump_json()

                if existing_row is not None:
                    try:
                        old_data = json.loads(existing_row[0])
                        old_desc = len((old_data.get("job") or {}).get("description") or "")
                        old_hist = len(old_data.get("client_recent_history") or [])
                        new_desc = len(job.job.description or "")
                        new_hist = len(job.client_recent_history or [])
                        if new_desc > old_desc or new_hist > old_hist or not old_data.get("posted_raw"):
                            conn.execute("UPDATE jobs SET job_json = ? WHERE job_id = ?", (job_json, key))
                            conn.commit()
                            return True
                    except Exception:
                        pass
                    self.duplicates_count += 1
                    conn.commit()
                    return False

                # Ensure seen_ids contains key
                conn.execute("INSERT OR IGNORE INTO seen_ids (job_id) VALUES (?)", (key,))
                # Insert to jobs
                conn.execute("INSERT INTO jobs (job_id, job_json) VALUES (?, ?)", (key, job_json))
                conn.commit()
                return True
            except Exception as e:
                conn.rollback()
                print(f"Error adding job to DB: {e}")
                return False

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
