"""Schema v1. PostgreSQL in production; SQLite is supported for offline tests."""
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy import (JSON, Column, Float, ForeignKey, Integer, MetaData,
                        String, Table, Text, UniqueConstraint, create_engine,
                        insert, select, update)

metadata = MetaData()
runs = Table("pipeline_runs", metadata,
    Column("id", String, primary_key=True), Column("start_date", String),
    Column("end_date", String), Column("timezone", String),
    Column("status", String), Column("phase", String),
    Column("created_at", Float), Column("finished_at", Float),
    Column("page", Integer, default=1), Column("discovery_done", Integer, default=0),
    Column("last_page_fingerprint", String, default=""),
    Column("error", Text, default=""), Column("retry_at", Float, default=0),
    Column("report", String, default=""), Column("delivery", String, default="pending"),
    Column("delivery_attempts", Integer, default=0), Column("delivery_retry_at", Float, default=0),
    Column("delivery_error", Text, default=""), Column("scheduled_for", String, unique=True))
jobs = Table("pipeline_jobs", metadata,
    Column("id", String, primary_key=True), Column("posted_date", String, index=True),
    Column("data", JSON), Column("raw_path", String),
    Column("first_seen", Float), Column("last_seen", Float))
queue = Table("pipeline_queue", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, ForeignKey(runs.c.id), index=True),
    Column("job_id", String), Column("url", Text), Column("card", JSON),
    Column("status", String, default="pending"), Column("attempts", Integer, default=0),
    Column("retry_at", Float, default=0), Column("worker", String, default=""),
    Column("error", Text, default=""), Column("result", JSON),
    UniqueConstraint("run_id", "job_id"))
events = Table("pipeline_events", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("run_id", String, index=True), Column("at", Float),
    Column("kind", String), Column("message", Text))
control = Table("pipeline_control", metadata,
    Column("id", Integer, primary_key=True), Column("settings", JSON),
    Column("remote_control", Integer, default=0))
workers = Table("pipeline_workers", metadata,
    Column("id", String, primary_key=True), Column("heartbeat", Float),
    Column("action", String), Column("url", Text), Column("saved", Integer))
alerts = Table("pipeline_alerts", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True), Column("run_id", String),
    Column("message", Text), Column("status", String, default="pending"),
    Column("attempts", Integer, default=0), Column("retry_at", Float, default=0))
DEFAULTS = {"enabled": False, "time": "07:00", "timezone": "Asia/Kolkata",
            "mode": "yesterday", "days": 1, "start_date": "", "end_date": "",
            "jobs_per_minute": 6, "search_delay_seconds": 10,
            "deliver_to_chat": False}
ACTIVE = ("queued", "running", "paused", "needs_login", "needs_verification", "cooldown", "attention")


def now():
    return datetime.now(timezone.utc).timestamp()


class Database:
    def __init__(self, url):
        options = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False, "timeout": 30}
        elif url.startswith("postgresql"):
            options["connect_args"] = {"connect_timeout": 10}
        self.engine = create_engine(url, **options)

    def init(self):
        metadata.create_all(self.engine)
        with self.engine.begin() as c:
            if not c.execute(select(control)).first():
                c.execute(insert(control).values(id=1, settings=DEFAULTS))

    def settings(self, c=None):
        if c is not None:
            return dict(c.execute(select(control.c.settings).where(control.c.id == 1)).scalar_one())
        with self.engine.connect() as conn:
            return self.settings(conn)

    def event(self, run_id, kind, message):
        with self.engine.begin() as c:
            c.execute(insert(events).values(run_id=run_id, at=now(), kind=kind, message=message[:2000]))

    def get_run(self, run_id):
        with self.engine.connect() as c:
            row = c.execute(select(runs).where(runs.c.id == run_id)).mappings().first()
            return dict(row) if row else None

    def change(self, run_id, **values):
        with self.engine.begin() as c:
            c.execute(update(runs).where(runs.c.id == run_id).values(**values))

    def create_run(self, start, end, tz, scheduled_for=None):
        with self.engine.begin() as c:
            # Serialise manual starts and scheduler starts through one database row.
            locked = c.execute(select(control).where(control.c.id == 1).with_for_update()).mappings().one()
            if locked["remote_control"]:
                raise ValueError("Release remote browser control before starting collection")
            if c.execute(select(runs.c.id).where(runs.c.status.in_(ACTIVE))).first():
                raise ValueError("A run already exists. Resume or stop it first.")
            if scheduled_for and c.execute(select(runs.c.id).where(runs.c.scheduled_for == scheduled_for)).first():
                return None
            rid = uuid.uuid4().hex
            c.execute(insert(runs).values(id=rid, start_date=start, end_date=end,
                timezone=tz, status="queued", phase="discovery", created_at=now(),
                scheduled_for=scheduled_for))
            return rid

    def enqueue(self, rid, cards):
        with self.engine.begin() as c:
            for card in cards:
                if c.execute(select(queue.c.id).where(queue.c.run_id == rid,
                                                     queue.c.job_id == card["job_id"])).first():
                    continue
                c.execute(insert(queue).values(run_id=rid, job_id=card["job_id"],
                    url=card["job_url"], card=card, status="pending", attempts=0, retry_at=0))

    def claim(self, rid, worker):
        with self.engine.begin() as c:
            row = c.execute(select(queue).where(queue.c.run_id == rid,
                queue.c.status == "pending", queue.c.retry_at <= now())
                .order_by(queue.c.id).with_for_update(skip_locked=True).limit(1)).mappings().first()
            if not row:
                return None
            # Conditional update also protects SQLite/local concurrent threads.
            result = c.execute(update(queue).where(queue.c.id == row["id"], queue.c.status == "pending")
                .values(status="running", worker=worker, attempts=row["attempts"] + 1))
            if result.rowcount != 1:
                return None
            return dict(row)

    def save(self, item, data, posted_date, raw_path):
        with self.engine.begin() as c:
            existing = c.execute(select(jobs).where(jobs.c.id == item["job_id"]).with_for_update()).mappings().first()
            # Never replace a valid description with an incomplete extraction.
            if existing and not (data.get("job") or {}).get("description"):
                raise ValueError("Incomplete result would replace saved job")
            values = dict(posted_date=posted_date, data=data, raw_path=raw_path, last_seen=now())
            if existing:
                c.execute(update(jobs).where(jobs.c.id == item["job_id"]).values(**values))
            else:
                c.execute(insert(jobs).values(id=item["job_id"], first_seen=now(), **values))
            c.execute(update(queue).where(queue.c.id == item["id"]).values(status="done", result=data, error=""))

    def counts(self, rid):
        from sqlalchemy import func
        with self.engine.connect() as c:
            return dict(c.execute(select(queue.c.status, func.count()).where(queue.c.run_id == rid)
                                  .group_by(queue.c.status)).all())

    def beat(self, wid, action, url="", saved=0):
        with self.engine.begin() as c:
            values = dict(heartbeat=now(), action=action, url=url, saved=saved)
            if c.execute(select(workers.c.id).where(workers.c.id == wid)).first():
                c.execute(update(workers).where(workers.c.id == wid).values(**values))
            else:
                c.execute(insert(workers).values(id=wid, **values))
