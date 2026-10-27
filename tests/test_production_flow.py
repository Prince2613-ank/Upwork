"""Production-flow regression tests. All browser/network interactions are mocked."""
import copy
import json
import os
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert, select, update

from server.app import create_app
from server.auth import COOKIE, CSRF_COOKIE, hash_password, verify_password
from server.browser import BrowserIssue, classify, retry_after
from server.config import Settings
from server.db import Database, control, jobs, login_limits, now, queue, releases, runs, sessions
from server.pipeline import Pipeline, schedule_tick
from server.quality import release_candidate
from server.reports import build_report

PASSWORD = "a-unique-test-password-for-dashboard"
PASSWORD_HASH = hash_password(PASSWORD)
HEADERS = {"X-Requested-With": "pipeline-dashboard"}


@pytest.fixture(params=["sqlite"] + (["postgresql"] if os.getenv("TEST_POSTGRES_URL") else []))
def settings(tmp_path, request):
    database_url = f"sqlite:///{tmp_path / 'app.db'}"
    owner = None
    if request.param == "postgresql":
        import uuid
        from sqlalchemy import create_engine, text
        from sqlalchemy.engine import make_url
        schema = "flow_" + uuid.uuid4().hex
        owner = create_engine(os.environ["TEST_POSTGRES_URL"], connect_args={"connect_timeout":10})
        with owner.begin() as c:
            c.execute(text(f'CREATE SCHEMA "{schema}"'))
        database_url = make_url(os.environ["TEST_POSTGRES_URL"]).update_query_dict({"options":f"-csearch_path={schema}"}).render_as_string(hide_password=False)
    result = replace(Settings(), database_url=f"sqlite:///{tmp_path / 'app.db'}", data_dir=tmp_path,
        username="admin", password="", password_hash=PASSWORD_HASH, session_secure=False,
        trust_proxy=False, public_url="http://testserver", webhook="", chat_space="", token_file=str(tmp_path / "missing"))
    result.prepare()
    result = replace(result, database_url=database_url)
    yield result
    if owner is not None:
        with owner.begin() as c:
            c.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        owner.dispose()


@pytest.fixture
def db(settings):
    db = Database(settings.database_url)
    db.init()
    yield db
    db.engine.dispose()


@pytest.fixture
def client(settings):
    with TestClient(create_app(settings)) as client:
        yield client


def sign_in(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 200, response.text
    return dict(HEADERS, **{"X-CSRF-Token": client.cookies.get(CSRF_COOKIE)})


def card(jid="~02123"):
    return {"job_id": jid, "job_url": f"https://www.upwork.com/jobs/{jid}", "posted_time": "1 day ago", "job_title": "Example"}


def data(jid="~02123"):
    return {"job_id": jid, "job_title": "Example project", "job_url": f"https://www.upwork.com/jobs/{jid}",
        "posted_at": "2020-01-02T06:00:00+00:00", "posted_date_precision": "exact",
        "job": {"description": "A complete description of the project and its deliverables.", "budget": "$500", "skills": ["Python"]},
        "client": {"location": "India", "total_spent": "$5000"}, "description_full": True,
        "history_expansion_complete": True, "client_recent_history": [
            {"job_title": "Past contract", "date": "2019", "freelancer_name": "Developer", "amount": "$200",
             "feedback": "The client gave clear requirements and paid on time.", "feedback_full": True,
             "direction": "freelancer_to_client"}]}


def new_run(db):
    return db.create_run("2020-01-02", "2020-01-02", "Asia/Kolkata")


def save_result(db, rid, result):
    db.enqueue(rid, [card(result["job_id"])])
    db.save(db.claim(rid, "A"), result, "2020-01-02", "raw.gz")


def test_login_page_replaces_basic_auth_prompt(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303 and response.headers["location"] == "/login"
    assert client.get("/login").status_code == 200
    response = client.get("/api/status")
    assert response.status_code == 401 and "www-authenticate" not in response.headers
    assert client.get("/dashboard.js").status_code == 401


def test_login_csrf_logout_and_cookie_flags(client):
    headers = sign_in(client)
    cookies = client.cookies.get(COOKIE)
    assert cookies
    assert client.get("/").status_code == 200
    assert client.get("/api/auth/me").json()["username"] == "admin"
    assert client.post("/api/auth/logout", json={}, headers=HEADERS).status_code == 403
    assert client.post("/api/auth/logout", json={}, headers=headers).status_code == 200
    assert client.get("/api/status").status_code == 401


def test_cross_origin_login_and_mutations_rejected(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD},
                           headers=dict(HEADERS, Origin="https://other.example"))
    assert response.status_code == 403


def test_login_rate_limit_is_persistent(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"}, headers=HEADERS).status_code == 401
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD}, headers=HEADERS)
    assert response.status_code == 429 and int(response.headers["retry-after"]) > 0


def test_sessions_survive_restart_and_password_rotation_revokes(settings):
    with TestClient(create_app(settings)) as first:
        sign_in(first)
        cookies = dict(first.cookies)
    with TestClient(create_app(settings)) as restarted:
        restarted.cookies.update(cookies)
        assert restarted.get("/api/status").status_code == 200
    with TestClient(create_app(replace(settings, password_hash=hash_password("a-new-long-password-after-reset")))) as rotated:
        rotated.cookies.update(cookies)
        assert rotated.get("/api/status").status_code == 401


def test_session_expiry(client):
    sign_in(client)
    with client.app.state.db.engine.begin() as c:
        c.execute(update(sessions).values(expires_at=now() - 1))
    assert client.get("/api/status").status_code == 401


def test_secure_cookie_configuration(settings):
    with TestClient(create_app(replace(settings, session_secure=True)), base_url="https://testserver") as secure:
        response = secure.post("/api/auth/login", json={"username":"admin","password":PASSWORD},headers=HEADERS)
        assert response.status_code == 200
        cookies = response.headers.get_list("set-cookie")
        assert all("Secure" in value and "SameSite=strict" in value for value in cookies)
        assert "HttpOnly" in next(value for value in cookies if value.startswith(COOKIE + "="))


@pytest.mark.parametrize("change,reason", [
    (lambda d:d["job"].update(description="  "), "missing_description"),
    (lambda d:d["job"].update(description="- ... !"), "missing_description"),
    (lambda d:d.update(client_recent_history=[]), "no_freelancer_reviews"),
    (lambda d:d["client_recent_history"][0].update(feedback="No feedback given"), "no_freelancer_reviews"),
])
def test_only_no_description_or_no_written_review_is_excluded(change, reason):
    record = data()
    change(record)
    approved, actual = release_candidate(record)
    assert approved is None and actual == reason


@pytest.mark.parametrize("change", [
    lambda d:d["job"].update(description="A truncated description..."),
    lambda d:d["client_recent_history"][0].update(feedback="Some text..."),
    lambda d:d["client_recent_history"][0].update(feedback_full=False),
    lambda d:d["client_recent_history"][0].update(direction="client_to_freelancer"),
    lambda d:d.update(history_expansion_complete=False),
])
def test_incomplete_extraction_details_no_longer_exclude(change):
    record = data()
    change(record)
    approved, reason = release_candidate(record)
    assert approved is not None and reason == "ready"


def test_valid_release_keeps_all_complete_reviews():
    record = data()
    record["client_recent_history"] *= 40
    approved, reason = release_candidate(record)
    assert reason == "ready" and len(approved["client_recent_history"]) == 40


def test_one_html_excludes_invalid_jobs_but_preserves_database(db, settings):
    rid = new_run(db)
    good = data()
    good["job_title"] = '<script>alert("unsafe")</script> Approved project'
    no_description = data("~02222")
    no_description["job"]["description"] = ""
    no_description["job_title"] = "EXCLUDE_NO_DESCRIPTION"
    no_reviews = data("~02333")
    no_reviews["client_recent_history"] = []
    no_reviews["job_title"] = "EXCLUDE_ZERO_REVIEWS"
    for record in (good, no_description, no_reviews):
        save_result(db, rid, record)
    db.change(rid, discovery_done=1)
    filename, partial = build_report(db, settings, db.get_run(rid))
    report = (settings.data_dir / "reports" / filename).read_text(encoding="utf-8")
    assert "Approved project" in report and "The client gave clear requirements" in report
    assert "EXCLUDE_NO_DESCRIPTION" not in report and "EXCLUDE_ZERO_REVIEWS" not in report
    assert "<script>alert" not in report and "\\u003cscript>alert" in report
    assert not partial
    assert len(list((settings.data_dir / "reports").iterdir())) == 1
    with db.engine.connect() as c:
        assert len(c.execute(select(jobs)).all()) == 3
        summary = c.execute(select(releases.c.summary)).scalar_one()
        assert summary["released"] == 1 and summary["excluded"] == 2


def test_current_snapshot_does_not_inherit_old_unverified_reviews(db):
    rid = new_run(db)
    old = data()
    old["job"]["description"] *= 4
    old["client_recent_history"][0].pop("direction")
    save_result(db, rid, old)
    db.change(rid, status="completed")
    next_run = new_run(db)
    save_result(db, next_run, data())
    with db.engine.connect() as c:
        snapshot = c.execute(select(queue.c.result).where(queue.c.run_id == next_run)).scalar_one()
        assert release_candidate(snapshot)[1] == "ready"
        assert len(c.execute(select(jobs.c.data)).scalar_one()["job"]["description"]) > len(snapshot["job"]["description"])


def test_persistent_5xx_exhausts_retries(db, settings):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card()])
    def fail(*_):
        raise BrowserIssue("temporary", "HTTP 503")
    pipeline = Pipeline(settings, db)
    for _ in range(3):
        pipeline.last_attempt["A"] = 0
        with db.engine.begin() as c:
            c.execute(update(queue).values(retry_at=0))
        pipeline.process_item(rid, "A", SimpleNamespace(detail=fail))
    assert db.counts(rid) == {"failed": 1}


@pytest.mark.parametrize("kind", ["cooldown", "needs_login", "needs_verification", "blocked"])
def test_global_access_problems_pause_without_consuming_job_retry_budget(db, settings, kind):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card()])
    def fail(*_):
        raise BrowserIssue(kind, "Action required", 600)
    Pipeline(settings, db).process_item(rid, "A", SimpleNamespace(detail=fail))
    assert db.get_run(rid)["status"] == kind
    with db.engine.connect() as c:
        assert c.execute(select(queue.c.attempts)).scalar_one() == 0


def test_url_timeout_resets_tab_and_saves_retry(db, settings):
    rid = new_run(db)
    db.change(rid, status="running")
    db.enqueue(rid, [card()])
    resets = []
    def jam(*_):
        raise TimeoutError("URL did not load")
    Pipeline(settings, db).process_item(rid, "A", SimpleNamespace(detail=jam, reset_page=lambda:resets.append(True)))
    assert resets == [True] and db.counts(rid) == {"pending": 1}


def test_worker_recovery_is_bounded(db, settings):
    rid = new_run(db)
    pipeline = Pipeline(settings, db)
    for attempt in range(3):
        db.change(rid, status="running")
        pipeline.recover_worker(rid, "A", RuntimeError("Browser offline"))
    assert db.get_run(rid)["status"] == "attention"


def test_account_block_and_retry_after():
    with pytest.raises(BrowserIssue) as issue:
        classify(200, "https://www.upwork.com/", "", "Your account has been suspended")
    assert issue.value.kind == "blocked"
    assert retry_after("Mon, 26 Oct 2026 02:00:00 GMT",datetime(2026,10,26,1,30,tzinfo=timezone.utc)) == 1800


def test_date_window_start_then_live_feed_and_final_download(client, settings):
    headers = sign_in(client)
    response = client.post("/api/runs", json={"start_date":"2020-01-02","end_date":"2020-01-02"}, headers=headers)
    rid = response.json()["id"]
    assert client.post("/api/runs", json={"start_date":"2020-01-02","end_date":"2020-01-02"}, headers=headers).status_code == 409
    db = client.app.state.db
    db.change(rid, status="running", discovery_done=1)
    save_result(db, rid, data())
    assert client.get("/api/live-feed",params={"run_id":rid}).json()[0]["release_check"] == "ready"
    Pipeline(settings, db).finish_ready()
    status = client.get("/api/status").json()["runs"][0]
    assert status["status"] == "completed" and status["release"]["released"] == 1
    download = client.get(f"/api/runs/{rid}/export/html")
    assert download.status_code == 200 and "attachment" in download.headers["content-disposition"]
    assert "The client gave clear requirements" in download.text


def test_scheduler_yesterday_ist_and_idempotence(db):
    with db.engine.begin() as c:
        config = db.settings(c)
        config.update(enabled=True,time="07:00",timezone="Asia/Kolkata")
        c.execute(update(control).values(settings=config))
    assert schedule_tick(db,datetime(2026,10,26,1,29,tzinfo=timezone.utc)) is None
    rid = schedule_tick(db,datetime(2026,10,26,1,30,tzinfo=timezone.utc))
    assert db.get_run(rid)["start_date"] == "2026-10-25"
    db.change(rid,status="completed")
    assert schedule_tick(db,datetime(2026,10,26,9,tzinfo=timezone.utc)) is None
