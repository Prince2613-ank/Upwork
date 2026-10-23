import sqlite3
import time
from pathlib import Path
from typing import Optional, Dict, Any

class QueueDB:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS queue (
                    job_id TEXT PRIMARY KEY,
                    job_url TEXT,
                    card_json TEXT,
                    status INTEGER DEFAULT 0,
                    claimed_by TEXT
                )
            """)
            conn.commit()

    def add_jobs(self, jobs_list: list):
        import json
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            for job in jobs_list:
                job_id = job.get("job_id")
                job_url = job.get("job_url")
                if not job_id:
                    continue
                try:
                    conn.execute("""
                        INSERT INTO queue (job_id, job_url, card_json, status)
                        VALUES (?, ?, ?, 0)
                    """, (job_id, job_url, json.dumps(job)))
                except sqlite3.IntegrityError:
                    pass
            conn.commit()

    def claim_next(self, worker_id: str) -> Optional[Dict[str, Any]]:
        import json
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            cursor = conn.cursor()
            conn.execute("BEGIN IMMEDIATE")
            
            cursor.execute("SELECT job_id, card_json FROM queue WHERE status = 0 LIMIT 1")
            row = cursor.fetchone()
            
            if row:
                job_id, card_json = row
                cursor.execute("UPDATE queue SET status = 1, claimed_by = ? WHERE job_id = ?", (worker_id, job_id))
                conn.commit()
                return json.loads(card_json)
            
            conn.commit()
            return None

    def mark_done(self, job_id: str):
        with sqlite3.connect(self.db_path, timeout=10) as conn:
            conn.execute("UPDATE queue SET status = 2 WHERE job_id = ?", (job_id,))
            conn.commit()
