import gzip
import hashlib
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select, text, update

from server.browser import BrowserIssue, BrowserSession, card_date
from server.config import Settings
from server.db import ACTIVE, Database, alerts, control, jobs, now, queue, runs, workers
from server.notifications import alert, upload_report
from server.reports import build_report

log = logging.getLogger(__name__)


def setup():
    settings = Settings()
    settings.prepare()
    db = Database(settings.database_url)
    db.init()
    return settings, db


def schedule_tick(db, reference=None):
    config = db.settings()
    current = reference or datetime.now(timezone.utc)
    local = current.astimezone(ZoneInfo(config["timezone"]))
    if not config["enabled"] or local.strftime("%H:%M") < config["time"]:
        return None
    if config["mode"] == "custom":
        start, end = config["start_date"], config["end_date"]
    else:
        end_day = local.date() - timedelta(days=1)
        start = (end_day - timedelta(days=config["days"] - 1)).isoformat()
        end = end_day.isoformat()
    key = f'{config["timezone"]}:{local.date().isoformat()}'
    try:
        return db.create_run(start, end, config["timezone"], key)
    except ValueError:
        return None  # Existing active run; retry the scheduling decision on next tick.


def schedule_main():
    _, db = setup()
    while True:
        try:
            schedule_tick(db)
        except Exception:
            log.exception("Scheduler tick failed")
        time.sleep(20)


class Pipeline:
    def __init__(self, settings, db):
        self.settings, self.db = settings, db
        self.claim_lock = threading.Lock()
        self.last_attempt = {"A": 0.0, "B": 0.0}

    def runnable(self, rid):
        return self.db.get_run(rid)["status"] == "running"

    def pause_issue(self, rid, issue):
        with self.db.engine.begin() as c:
            changed = c.execute(update(runs).where(runs.c.id == rid, runs.c.status == "running")
                .values(status=issue.kind, error=str(issue), retry_at=now() + max(60, issue.wait)))
        if not changed.rowcount:
            return
        self.db.event(rid, issue.kind, str(issue))
        self.notify(rid, f"Upwork collection {rid[:8]} paused: {issue}. Open dashboard to inspect/resume.")

    def notify(self, rid, message):
        if not self.db.settings()["deliver_to_chat"]:
            return
        with self.db.engine.begin() as c:
            c.execute(insert(alerts).values(run_id=rid, message=message, status="pending", attempts=0, retry_at=0))

    def flush_alerts(self):
        if not self.db.settings()["deliver_to_chat"]:
            return
        with self.db.engine.connect() as c:
            pending = c.execute(select(alerts).where(alerts.c.status == "pending", alerts.c.retry_at <= now())
                                .order_by(alerts.c.id).limit(5)).mappings().all()
        for item in pending:
            try:
                alert(self.settings, item["message"])
                with self.db.engine.begin() as c:
                    c.execute(update(alerts).where(alerts.c.id == item["id"]).values(status="sent"))
            except Exception:
                attempt = item["attempts"] + 1
                with self.db.engine.begin() as c:
                    c.execute(update(alerts).where(alerts.c.id == item["id"]).values(
                        attempts=attempt, status="failed" if attempt >= 5 else "pending",
                        retry_at=now() + min(3600, 60 * 2 ** attempt)))
                self.db.event(item["run_id"], "notification_failed", f"Alert attempt {attempt}; check webhook configuration/network")

    def diagnostics(self, session, rid, wid):
        if session is None:
            return
        try:
            session.page.screenshot(path=str(self.settings.data_dir / "diagnostics" / f"{rid}-{wid}.png"), timeout=5000)
        except Exception:
            pass

    def discover_page(self, rid, session):
        run = self.db.get_run(rid)
        tz = ZoneInfo(run["timezone"])
        cards = session.search(self.settings.search_url, run["page"])
        fingerprint = hashlib.sha256("|".join(card["job_id"] for card in cards).encode()).hexdigest()
        if fingerprint == run["last_page_fingerprint"]:
            raise ValueError("Search returned the same page twice; inspect pagination before resuming")
        oldest = date.fromisoformat(run["start_date"])
        newest = date.fromisoformat(run["end_date"])
        candidates, older = [], 0
        for card in cards:
            dt = card_date(card, tz)
            if dt is None:
                raise ValueError("Search posting date missing; cannot establish date coverage")
            # Coarse relative timestamps may straddle midnight: discover a margin,
            # then filter with detail timestamps. Never stop on a single old/pinned job.
            if dt < oldest - timedelta(days=1):
                older += 1
            if oldest - timedelta(days=1) <= dt <= newest + timedelta(days=1):
                candidates.append(card)
        self.db.enqueue(rid, candidates)
        done = older == len(cards)
        with self.db.engine.begin() as c:
            c.execute(update(runs).where(runs.c.id == rid).values(page=run["page"] + 1,
                last_page_fingerprint=fingerprint, discovery_done=int(done), phase="details" if done else "discovery"))
        self.db.event(rid, "discovery", f'Page {run["page"]}: {len(candidates)} candidates; cutoff={done}')
        if run["page"] >= 500 and not done:
            raise ValueError("Search safety cap reached without date cutoff; coverage needs review")

    def process_item(self, rid, wid, session):
        # Pacing is a ceiling on detail attempts, not a promise of achieved throughput.
        rpm = self.db.settings()["jobs_per_minute"]
        if time.monotonic() - self.last_attempt[wid] < 60 / rpm:
            return
        with self.claim_lock:
            item = self.db.claim(rid, wid)
        if not item:
            return
        self.last_attempt[wid] = time.monotonic()
        self.db.beat(wid, "Fetching job", item["url"])
        try:
            data, raw = session.detail(item["card"], lambda: self.runnable(rid))
            if not self.runnable(rid):
                self.release(item, "pending", "Paused during extraction")
                return
            run = self.db.get_run(rid)
            stamp = data.get("posted_at", "")
            if not stamp:
                raise ValueError("Missing posting timestamp")
            posted = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
            if posted.tzinfo is None:
                raise ValueError("Posting timestamp has no timezone")
            posting_date = posted.astimezone(ZoneInfo(run["timezone"])).date().isoformat()
            if not run["start_date"] <= posting_date <= run["end_date"]:
                self.release(item, "outside_window", "Outside selected dates after detail check")
                return
            # Preserve timestamp precision explicitly; relative labels are approximate.
            digest = hashlib.sha256(raw.encode()).hexdigest()
            raw_path = self.settings.data_dir / "raw" / f"{digest}.html.gz"
            if not raw_path.exists():
                with gzip.open(raw_path, "wt", encoding="utf-8") as f:
                    f.write(raw)
            self.db.save(item, data, posting_date, raw_path.name)
        except BrowserIssue as exc:
            self.release(item, "unavailable" if exc.kind == "unavailable" else "pending", str(exc), exc.wait)
            if exc.kind in ("cooldown", "needs_login", "needs_verification"):
                self.diagnostics(session, rid, wid)
                self.pause_issue(rid, exc)
        except Exception as exc:
            attempts = item["attempts"] + 1
            self.release(item, "failed" if attempts >= 3 else "pending", str(exc), 30 * 2 ** attempts)
            self.diagnostics(session, rid, wid)
            self.db.event(rid, "job_error", f'{item["job_id"]}: {str(exc)[:400]}')
            with self.db.engine.connect() as c:
                recent = c.execute(select(queue.c.status).where(queue.c.run_id == rid)
                                   .order_by(queue.c.id.desc()).limit(5)).scalars().all()
            if len(recent) == 5 and all(s == "failed" for s in recent):
                self.pause_issue(rid, BrowserIssue("attention", "Repeated extraction failures; inspect selectors/browser"))

    def release(self, item, status, error, wait=0):
        with self.db.engine.begin() as c:
            c.execute(update(queue).where(queue.c.id == item["id"]).values(
                status=status, error=error[:1000], retry_at=now() + wait))

    def worker(self, wid):
        endpoint = self.settings.browser_a if wid == "A" else self.settings.browser_b
        while True:
            self.db.beat(wid, "Waiting")
            with self.db.engine.connect() as c:
                run = c.execute(select(runs).where(runs.c.status == "running")
                                .order_by(runs.c.created_at).limit(1)).mappings().first()
            if not run:
                time.sleep(2)
                continue
            rid, session = run["id"], None
            try:
                self.db.beat(wid, "Connecting browser")
                with BrowserSession(endpoint) as session:
                    # Only A discovers; both consume once candidates are available.
                    if wid == "A" and not run["discovery_done"]:
                        self.db.beat(wid, f'Discovering page {run["page"]}')
                        self.discover_page(rid, session)
                        time.sleep(self.db.settings()["search_delay_seconds"])
                    if self.runnable(rid):
                        self.process_item(rid, wid, session)
            except BrowserIssue as exc:
                self.diagnostics(session, rid, wid)
                self.pause_issue(rid, exc if exc.kind in ("cooldown", "needs_login", "needs_verification")
                                 else BrowserIssue("attention", str(exc)))
            except Exception as exc:
                self.diagnostics(session, rid, wid)
                self.pause_issue(rid, BrowserIssue("attention", f"Worker {wid}: {type(exc).__name__}: {str(exc)[:300]}"))
            time.sleep(1)

    def finish_ready(self):
        with self.db.engine.connect() as c:
            active = c.execute(select(runs).where(runs.c.status == "running",
                runs.c.discovery_done == 1)).mappings().all()
        for row in active:
            run = dict(row)
            counts = self.db.counts(run["id"])
            if counts.get("pending") or counts.get("running"):
                continue
            filename, partial = build_report(self.db, self.settings, run)
            # Do not overwrite a concurrent dashboard pause/stop.
            with self.db.engine.begin() as c:
                changed = c.execute(update(runs).where(runs.c.id == run["id"], runs.c.status == "running")
                    .values(status="partial" if partial else "completed", phase="finished",
                            finished_at=now(), report=filename,
                            delivery="pending" if self.db.settings(c)["deliver_to_chat"] else "disabled"))
            if changed.rowcount:
                self.db.event(run["id"], "finished", f"Report ready: {filename}; counts={counts}")
                self.notify(run["id"], f'Upwork report ready: {run["start_date"]} to {run["end_date"]}. '
                    f'Saved {counts.get("done",0)}, failed {counts.get("failed",0)}. '
                    f'{self.settings.public_url}/api/runs/{run["id"]}/export/html')

    def deliver(self):
        with self.db.engine.connect() as c:
            pending = c.execute(select(runs).where(runs.c.report != "", runs.c.delivery.in_(("pending", "retry")),
                                                  runs.c.delivery_retry_at <= now())).mappings().all()
        for row in pending:
            run = dict(row)
            if not self.db.settings()["deliver_to_chat"]:
                continue
            try:
                upload_report(self.settings, run, self.settings.data_dir / "reports" / run["report"])
                self.db.change(run["id"], delivery="sent", delivery_error="")
            except Exception as exc:
                attempt = run["delivery_attempts"] + 1
                self.db.change(run["id"], delivery="failed" if attempt >= 5 else "retry",
                    delivery_attempts=attempt, delivery_retry_at=now() + min(3600, 60 * 2 ** attempt),
                    delivery_error=f'{type(exc).__name__}: Delivery failed; inspect OAuth, space permissions and attachment limits')
                self.db.event(run["id"], "delivery_failed", f"Attempt {attempt}; report remains downloadable")


def worker_main():
    settings, db = setup()
    # Keep a dedicated PostgreSQL connection holding a session advisory lock.
    # This prevents two supervisors/redeploys from processing the same queue.
    leader = db.engine.connect()
    if db.engine.dialect.name == "postgresql":
        if not leader.execute(text("SELECT pg_try_advisory_lock(84262201)")).scalar():
            raise RuntimeError("Another pipeline supervisor is already running")
        leader.commit()
    with db.engine.begin() as c:
        c.execute(update(queue).where(queue.c.status == "running").values(status="pending", error="Recovered after restart"))
    pipeline = Pipeline(settings, db)
    threads = [threading.Thread(target=pipeline.worker, args=(wid,), daemon=True) for wid in ("A", "B")]
    for thread in threads:
        thread.start()
    while True:
        try:
            # A lost lock connection must stop this supervisor before another takes over.
            leader.execute(text("SELECT 1"))
            leader.commit()
            with db.engine.begin() as c:
                c.execute(update(runs).where(runs.c.status == "queued").values(status="running"))
                c.execute(update(runs).where(runs.c.status == "cooldown", runs.c.retry_at <= now())
                          .values(status="running", error=""))
                stale = c.execute(select(workers.c.id).where(workers.c.heartbeat < now() - 180)).first()
            if stale or any(not thread.is_alive() for thread in threads):
                log.error("Worker stalled; exiting so container supervisor can recover queue")
                os._exit(70)
            pipeline.finish_ready()
            pipeline.flush_alerts()
            pipeline.deliver()
        except Exception:
            log.exception("Supervisor failed; exiting for controlled restart")
            raise
        time.sleep(3)


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    {"worker": worker_main, "scheduler": schedule_main}[sys.argv[1]]()
