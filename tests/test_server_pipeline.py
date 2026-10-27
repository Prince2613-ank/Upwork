"""Durability, operator control and failure-path tests; no live account access."""
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from server.app import create_app
from server.browser import BrowserIssue, classify, retry_after, valid_url
from server.config import Settings
from server.db import Database, alerts, control, events, jobs, now, queue, runs
from server.pipeline import Pipeline, schedule_tick
from server.reports import build_report, safe_csv


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.getenv("TEST_POSTGRES_URL") else []))
def db(tmp_path, request):
    if request.param == "sqlite":
        database = Database(f"sqlite:///{tmp_path / 'pipeline.db'}")
    else:
        import uuid
        from sqlalchemy import create_engine, text
        schema = "test_" + uuid.uuid4().hex
        engine = create_engine(os.environ["TEST_POSTGRES_URL"])
        with engine.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
        database = Database(os.environ["TEST_POSTGRES_URL"])
        database.engine = database.engine.execution_options(schema_translate_map={None: schema})
    database.init()
    yield database
    database.engine.dispose()
    if request.param == "postgresql":
        with engine.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()


@pytest.fixture
def config(tmp_path):
    config = replace(Settings(), data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'api.db'}",
                     password="a-long-test-password", password_hash="", session_secure=False, webhook="", chat_space="", token_file=str(tmp_path / "missing.json"))
    config.prepare()
    return config


def card(jid="~02123"):
    return {"job_id": jid, "job_url": f"https://www.upwork.com/jobs/{jid}", "posted_time": "1 day ago", "job_title": "Test job"}


def result():
    return {"job_id": "~02123", "job_title": '<script>alert("x")</script>',
            "job_url": "https://www.upwork.com/jobs/~02123", "posted_at": "2020-01-02T06:00:00+00:00",
            "posted_date_precision": "exact", "job": {"description": "Real full description"},
            "client": {"location": "India"}, "client_recent_history": [{"job_title": "Project", "feedback": "Great client to work with", "rating": "5.0", "freelancer_name": "Alice"}],
            "history_expansion_complete": True, "extraction_status": {"full_reviews": True}}


def new_run(db):
    return db.create_run("2020-01-02", "2020-01-02", "Asia/Kolkata")


def test_only_one_active_run(db):
    rid = new_run(db)
    with pytest.raises(ValueError, match="already"):
        new_run(db)
    db.change(rid, status="completed")
    assert new_run(db) != rid


def test_queue_dedup_and_claim(db):
    rid = new_run(db)
    db.enqueue(rid, [card(), card()])
    item = db.claim(rid, "A")
    assert item["job_id"] == "~02123"
    assert db.claim(rid, "B") is None
    assert db.counts(rid) == {"running": 1}


def test_concurrent_claims_are_distinct(db):
    from concurrent.futures import ThreadPoolExecutor
    rid = new_run(db)
    db.enqueue(rid, [card(f"~02{i}") for i in range(12)])
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(pool.map(lambda wid: db.claim(rid, wid), ["A", "B"] * 6))
    ids = [item["id"] for item in claims if item]
    assert len(ids) == len(set(ids))
    assert ids


def test_save_persists_snapshot_and_updates_existing(db):
    rid = new_run(db)
    db.enqueue(rid, [card()])
    item = db.claim(rid, "A")
    db.save(item, result(), "2020-01-02", "hash.html.gz")
    assert db.counts(rid) == {"done": 1}
    db.change(rid, status="completed")
    rid2 = new_run(db)
    db.enqueue(rid2, [card()])
    data = result()
    data["job"]["description"] = "Updated full description"
    db.save(db.claim(rid2, "B"), data, "2020-01-02", "new.html.gz")
    with db.engine.connect() as c:
        assert len(c.execute(select(jobs)).all()) == 1
        assert c.execute(select(queue.c.result).where(queue.c.run_id == rid)).scalar_one()["job"]["description"] == "Real full description"


def test_scheduler_ist_boundary_idempotence_and_restart_catchup(db):
    with db.engine.begin() as c:
        config = db.settings(c)
        config.update(enabled=True, time="07:00", timezone="Asia/Kolkata")
        c.execute(update(control).values(settings=config))
    assert schedule_tick(db, datetime(2026, 10, 26, 1, 29, tzinfo=timezone.utc)) is None
    rid = schedule_tick(db, datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc))
    assert db.get_run(rid)["start_date"] == "2026-10-25"
    db.change(rid, status="completed")
    assert schedule_tick(db, datetime(2026, 10, 26, 9, tzinfo=timezone.utc)) is None
    assert schedule_tick(db, datetime(2026, 10, 27, 9, tzinfo=timezone.utc))


def test_disabled_schedule_does_not_start(db):
    assert schedule_tick(db, datetime(2026, 10, 26, 9, tzinfo=timezone.utc)) is None


@pytest.mark.parametrize("args,kind", [
    ((429, "https://www.upwork.com/jobs/1", "", "", {"retry-after": "600"}), "cooldown"),
    ((200, "https://www.upwork.com/ab/account-security/login", "", ""), "needs_login"),
    ((200, "https://www.upwork.com/", "Just a moment...", ""), "needs_verification"),
    ((403, "https://www.upwork.com/", "", ""), "needs_verification"),
    ((404, "https://www.upwork.com/jobs/1", "", ""), "unavailable"),
    ((503, "https://www.upwork.com/", "", ""), "temporary"),
])
def test_classify_failures(args, kind):
    with pytest.raises(BrowserIssue) as error:
        classify(*args)
    assert error.value.kind == kind


def test_retry_after_date_and_missing():
    assert retry_after("Mon, 26 Oct 2026 02:00:00 GMT", datetime(2026, 10, 26, 1, 30, tzinfo=timezone.utc)) == 1800
    assert retry_after(None) == 900
    assert retry_after("-1") == 0


def test_url_allowlist():
    assert valid_url("https://www.upwork.com/jobs/~02123")
    for url in ("https://upwork.com.evil.test/", "http://www.upwork.com/", "javascript:alert(1)", "https://user@upwork.com/"):
        assert not valid_url(url)


def test_report_escapes_content_and_marks_partial(db, config):
    rid = new_run(db)
    db.enqueue(rid, [card()])
    data = result()
    data["posted_date_precision"] = "parsed_or_relative"
    db.save(db.claim(rid, "A"), data, "2020-01-02", "")
    db.change(rid, discovery_done=1)
    filename, partial = build_report(db, config, db.get_run(rid))
    html = (config.data_dir / "reports" / filename).read_text(encoding="utf-8")
    assert partial
    assert '<script>alert' not in html
    assert '\\u003cscript>alert' in html
    assert json.loads((config.data_dir / "reports" / filename).with_suffix(".json").read_text())[0]["job_id"] == "~02123"
    assert safe_csv("  =HYPERLINK()") == "'  =HYPERLINK()"


def test_failure_preserves_pending_work_and_pauses_all(db, config):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card()])
    def blocked(*_):
        raise BrowserIssue("cooldown", "Rate limited", 600)
    pipeline = Pipeline(config, db)
    pipeline.process_item(rid, "A", SimpleNamespace(detail=blocked))
    run = db.get_run(rid)
    assert run["status"] == "cooldown"
    assert run["retry_at"] > now() + 590
    assert db.counts(rid) == {"pending": 1}


def test_successful_processing_filters_selected_day(db, config):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card()])
    Pipeline(config, db).process_item(rid, "A", SimpleNamespace(detail=lambda *_: (result(), "<html>job</html>")))
    assert db.counts(rid) == {"done": 1}
    assert list((config.data_dir / "raw").glob("*.gz"))


def test_outside_window_is_not_saved(db, config):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card()])
    data = result()
    data["posted_at"] = "2020-01-01T00:00:00+00:00"
    Pipeline(config, db).process_item(rid, "A", SimpleNamespace(detail=lambda *_: (data, "raw")))
    assert db.counts(rid) == {"outside_window": 1}


def test_pacing_prevents_second_attempt_in_interval(db, config):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card(), card("~02456")])
    pipeline = Pipeline(config, db)
    session = SimpleNamespace(detail=lambda *_: (result(), "raw"))
    pipeline.process_item(rid, "A", session)
    pipeline.process_item(rid, "A", session)
    assert db.counts(rid) == {"done": 1, "pending": 1}


def test_repeated_search_page_pauses_instead_of_infinite_loop(db, config, monkeypatch):
    from datetime import date
    monkeypatch.setattr("server.pipeline.card_date", lambda *_: date(2020, 1, 2))
    rid = new_run(db)
    pipeline = Pipeline(config, db)
    session = SimpleNamespace(search=lambda *_: [card()])
    pipeline.discover_page(rid, session)
    with pytest.raises(ValueError, match="same page"):
        pipeline.discover_page(rid, session)


def test_delivery_failure_does_not_restart_scraping(db, config, monkeypatch):
    rid = new_run(db)
    db.change(rid, status="completed", report=f"{rid}.html", delivery="pending")
    with db.engine.begin() as c:
        options = db.settings(c)
        options["deliver_to_chat"] = True
        c.execute(update(control).values(settings=options))
    def fail(*_):
        raise RuntimeError("No credentials")
    monkeypatch.setattr("server.pipeline.upload_report", fail)
    Pipeline(config, db).deliver()
    run = db.get_run(rid)
    assert run["status"] == "completed"
    assert run["delivery"] == "retry"
    assert run["delivery_attempts"] == 1


def test_api_auth_controls_validation_and_csrf(config):
    app = create_app(config)
    headers = {"X-Requested-With": "pipeline-dashboard"}
    with TestClient(app) as client:
        assert client.get("/api/status").status_code == 401
        login = client.post('/api/auth/login', json={'username':config.username,'password':config.password}, headers=headers)
        assert login.status_code == 200
        assert client.get("/").status_code == 200
        assert client.post("/api/runs", json={}).status_code == 403
        headers['X-CSRF-Token'] = client.cookies.get('flodata_csrf')
        assert client.post("/api/runs", json={"start_date": "2020-02-02", "end_date": "2020-01-01"}, headers=headers).status_code == 422
        assert client.post("/api/runs", json={"start_date": "2020-01-01", "end_date": "2020-01-01", "timezone": "invalid"}, headers=headers).status_code == 422
        rid = client.post("/api/runs", json={"start_date": "2020-01-01", "end_date": "2020-01-01"}, headers=headers).json()["id"]
        assert client.get("/api/remote-ready").status_code == 409
        assert client.post(f"/api/runs/{rid}/pause", json={}, headers=headers).status_code == 200
        assert client.post(f"/api/runs/{rid}/compile", json={}, headers=headers).status_code == 200
        assert client.get(f"/api/runs/{rid}/export/html").status_code == 200
        assert client.get("/api/remote-ready").status_code == 409
        assert client.post('/api/browser/take-control', json={}, headers=headers).status_code == 200
        assert client.get("/api/remote-ready").status_code == 200
        assert client.post(f"/api/runs/{rid}/resume", json={}, headers=headers).status_code == 409
        with app.state.db.engine.begin() as c:
            c.execute(update(control).values(remote_control=0))
        assert client.post(f"/api/runs/{rid}/resume", json={}, headers=headers).status_code == 200
        bad = dict(client.get("/api/schedule").json(), jobs_per_minute=25)
        assert client.put("/api/schedule", json=bad, headers=headers).status_code == 422
        chat = dict(client.get("/api/schedule").json(), deliver_to_chat=True)
        assert client.put("/api/schedule", json=chat, headers=headers).status_code == 409


def test_sqlite_import_deduplicates_without_modifying_source(db, config, tmp_path):
    import sqlite3
    from server.admin import import_sqlite
    source = tmp_path / "legacy.db"
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE jobs(job_id TEXT PRIMARY KEY, job_json TEXT, raw_html TEXT)")
        c.execute("INSERT INTO jobs VALUES (?, ?, ?)", ("~02123", json.dumps(result()), "raw"))
    before = source.read_bytes()
    assert import_sqlite(config, db, [source])["imported_or_updated"] == 1
    assert import_sqlite(config, db, [source])["retained_existing"] == 1
    assert source.read_bytes() == before


def test_alert_outbox_survives_failure_and_retries(db, config, monkeypatch):
    with db.engine.begin() as c:
        options = db.settings(c)
        options["deliver_to_chat"] = True
        c.execute(update(control).values(settings=options))
    pipeline = Pipeline(config, db)
    rid = new_run(db)
    pipeline.notify(rid, "Login required")
    def fail(*_):
        raise RuntimeError("Network unavailable")
    monkeypatch.setattr("server.pipeline.alert", fail)
    pipeline.flush_alerts()
    with db.engine.begin() as c:
        item = c.execute(select(alerts)).mappings().one()
        assert item["attempts"] == 1 and item["status"] == "pending"
        c.execute(update(alerts).values(retry_at=0))
    sent = []
    monkeypatch.setattr("server.pipeline.alert", lambda *_: sent.append(True))
    pipeline.flush_alerts()
    with db.engine.connect() as c:
        assert c.execute(select(alerts.c.status)).scalar_one() == "sent"
    assert sent == [True]
