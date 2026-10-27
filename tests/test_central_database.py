"""Offline SQLite regression tests. Never starts a browser or touches real output."""
import ast
import csv
import html
import json
import re
import sqlite3
import tempfile
import threading
import unittest
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from collector.storage.central import CentralStore, iter_job_rows


def job(day, description="A complete description", reviews=None):
    return {"posted_at": day + "T12:00:00+00:00", "job_title": "Example",
            "job": {"description": description}, "client_recent_history": reviews or []}


class CentralDatabaseTests(unittest.TestCase):
    def setUp(self):
        self.test_root = (Path(__file__).resolve().parents[1] / "output" / "database-tests").resolve()
        self.test_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=self.test_root)
        self.directory = Path(self.temp.name)
        assert self.directory.resolve().is_relative_to(self.test_root)
        self.store = CentralStore(self.directory / "database.db")
        self.store.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_multiple_days_append_rows_in_one_file(self):
        self.store.save("one", job("2020-01-01"))
        self.store.save("two", job("2020-01-02"))
        self.assertEqual(self.store.ids(), {"one", "two"})
        self.assertEqual([p.name for p in self.directory.glob("*.db")], ["database.db"])

    def test_upsert_preserves_richer_content_and_first_seen(self):
        reviews = [{"job_title": "Contract", "date": "2020", "feedback": "A detailed freelancer review"}]
        self.store.save("one", job("2020-01-01", "A long and complete project description", reviews), "rich HTML")
        with self.store.connect() as c:
            c.execute("UPDATE jobs SET first_seen_at='2019-01-01' WHERE job_id='one'")
        self.store.save("one", job("2020-01-01", "Short"), "weak HTML")
        with self.store.connect() as c:
            rows = c.execute("SELECT job_json,first_seen_at,raw_html FROM jobs").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0][0])["client_recent_history"], reviews)
        self.assertEqual(rows[0][1], "2019-01-01")
        self.assertEqual(rows[0][2], "rich HTML")

    def test_runs_and_membership_are_rows(self):
        first = self.store.start_run("2020-01-01", "2020-01-01")
        self.store.save("one", job("2020-01-01"), run_id=first)
        self.store.finish_run(first)
        second = self.store.start_run("2020-01-01", "2020-01-02")
        self.store.save("one", job("2020-01-01"), run_id=second)
        with self.store.connect() as c:
            self.assertEqual(c.execute("SELECT count(*) FROM jobs").fetchone()[0], 1)
            self.assertEqual(c.execute("SELECT count(*) FROM collection_runs").fetchone()[0], 2)
            self.assertEqual(c.execute("SELECT count(*) FROM run_jobs").fetchone()[0], 2)

    def test_legacy_merge_is_non_destructive_and_idempotent(self):
        source = self.directory / "database_daily_2020-01-01.db"
        with sqlite3.connect(source) as c:
            c.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY,job_json TEXT,raw_html TEXT)")
            c.execute("INSERT INTO jobs VALUES(?,?,?)", ("one", json.dumps(job("2020-01-01")), "raw"))
        c.close()
        original = source.read_bytes()
        self.assertEqual(self.store.migrate_legacy(self.directory)["rows"], 1)
        self.assertEqual(self.store.migrate_legacy(self.directory)["rows"], 0)
        self.assertEqual(source.read_bytes(), original)
        self.assertTrue((self.directory / "backups" / "database_before_consolidation.db").exists())

    def test_additive_upgrade_backfills_dates(self):
        path = self.directory / "old.db"
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY,job_json TEXT)")
            c.execute("INSERT INTO jobs VALUES(?,?)", ("one", json.dumps(job("2020-01-01"))))
        c.close()
        store = CentralStore(path)
        store.initialize()
        self.assertEqual(store.ids("2020-01-01", "2020-01-01"), {"one"})

    def test_exports_filter_all_days_from_shared_database(self):
        for n in range(1, 4):
            self.store.save(str(n), job(f"2020-01-0{n}"), "HTML")
        rows = list(iter_job_rows(self.store.path, "2020-01-02", "2020-01-02", include_raw=True))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "2")
        self.assertEqual(rows[0][2], "HTML")

    def test_concurrent_workers_upsert_unique_rows(self):
        errors = []
        def work():
            try:
                for i in range(10):
                    self.store.save(str(i), job("2020-01-01"))
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=work) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertFalse(errors)
        self.assertEqual(len(self.store.ids()), 10)

    def test_daily_manager_changes_window_without_creating_files(self):
        # Exercise the actual manager class without importing/launching the app.
        if not Path("run_daily_system.py").exists():
            self.skipTest("run_daily_system.py removed in favor of server.pipeline")
        module = ast.parse(Path("run_daily_system.py").read_text(encoding="utf-8"))
        cls = next(n for n in module.body if isinstance(n, ast.ClassDef) and n.name == "DailyDatabaseManager")
        scope = dict(threading=threading, datetime=datetime, timedelta=timedelta, deque=deque,
            CentralStore=CentralStore, DB_MASTER=self.store.path, OUTPUT_DIR=self.directory,
            SESSION_STATE_FILE=self.directory / "session.json", json=json, sqlite3=sqlite3,
            html=html, re=re, time=__import__('time'), print=lambda *args, **kwargs: None, format_location=lambda x: x,
            restore_full_description_from_raw=lambda text, raw: text,
            restore_full_feedback_from_raw=lambda text, raw: text,
            clean_freelancer_review=lambda text, *args: text, update_live_dashboard_status=lambda: None)
        exec(compile(ast.Module(body=[cls], type_ignores=[]), "run_daily_system.py", "exec"), scope)
        manager = scope["DailyDatabaseManager"]()
        manager.set_target_range("2020-01-01", "2020-01-02")
        manager.init_current_database()
        manager.save_job(job("2020-01-01"), "one", "HTML")
        manager.save_job(job("2020-01-02"), "two", "HTML")
        self.assertEqual(manager.daily_saves_count, 2)
        manager.set_target_range("2020-01-02", "2020-01-02")
        self.assertEqual(manager.daily_saves_count, 1)
        self.assertEqual(manager.active_db_path, self.store.path)
        manager._export_csv(self.store.path, self.directory / "selected.csv")
        with (self.directory / "selected.csv").open(encoding="utf-8-sig") as f:
            self.assertEqual([r['job_id'] for r in csv.DictReader(f)], ["two"])
        self.assertEqual([p.name for p in self.directory.glob("*.db")], ["database.db"])
        self.assertEqual(self.store.ids(), {"one", "two"})


if __name__ == "__main__":
    unittest.main()
