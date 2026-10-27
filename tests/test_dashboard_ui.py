"""Login page, tabbed dashboard assets and the analytics endpoint of the server app."""
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import insert

from server.analytics import money, percent, spend_tier, timeline
from server.app import create_app
from server.config import Settings
from server.db import jobs, now

PASSWORD = "a-long-test-password"


@pytest.fixture
def config(tmp_path):
    config = replace(Settings(), data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'ui.db'}",
                     username="admin", password=PASSWORD, password_hash="", session_secure=False,
                     webhook="", chat_space="", token_file=str(tmp_path / "missing.json"))
    config.prepare()
    return config


def job(jid, day, country, spent, rate, with_review=True):
    history = [{"feedback": "Great client to work with.", "feedback_full": True,
                "direction": "freelancer_to_client"}] if with_review else []
    return dict(id=jid, posted_date=day, first_seen=now(), last_seen=now(), raw_path="", data={
        "job_title": f"Job {jid}", "job": {"description": "A complete description"},
        "client": {"location": country, "payment_verified": True, "total_spent": spent, "hire_rate": rate},
        "client_recent_history": history, "history_expansion_complete": True})


def sign_in(client):
    response = client.post("/api/auth/login", json={"username": "admin", "password": PASSWORD},
                           headers={"X-Requested-With": "pipeline-dashboard"})
    assert response.status_code == 200
    return response


def test_helpers_parse_upwork_strings():
    assert money("$17K total spent") == 17000
    assert money("$1.5M total spent") == 1_500_000
    assert money("no spend") is None
    assert percent("38%") == 38
    assert spend_tier(500) == "Under $1K" and spend_tier(17000) == "$10K–100K" and spend_tier(None) == "Unknown"
    gaps = timeline({"2026-10-01": 2, "2026-10-03": 5})
    assert [p["count"] for p in gaps] == [2, 0, 5]


def test_login_flow_and_pages(config):
    with TestClient(create_app(config)) as client:
        assert client.get("/", follow_redirects=False).status_code == 303
        login = client.get("/login")
        assert login.status_code == 200 and "login-form" in login.text
        assert client.post("/api/auth/login", json={"username": "admin", "password": "wrong"},
                           headers={"X-Requested-With": "pipeline-dashboard"}).status_code == 401
        sign_in(client)
        page = client.get("/")
        assert page.status_code == 200
        for marker in ('data-tab="overview"', 'id="chart-countries"', 'id="jobs"', 'id="schedule"'):
            assert marker in page.text
        assert client.get("/dashboard.js").status_code == 200
        # Signed-in users skip the login page.
        assert client.get("/login", follow_redirects=False).status_code == 303


def test_analytics_and_job_release_check(config):
    app = create_app(config)
    with TestClient(app) as client:
        assert client.get("/api/analytics").status_code == 401
        with app.state.db.engine.begin() as c:
            c.execute(insert(jobs), [job("~1", "2026-10-01", "Canada, Ottawa", "$17K total spent", "40%"),
                                     job("~2", "2026-10-01", "Canada, Toronto", "$500 total spent", "20%", with_review=False),
                                     job("~3", "2026-10-03", "India", "$2M total spent", "60%")])
        sign_in(client)
        data = client.get("/api/analytics").json()
        assert data["total"] == 3 and data["release_ready"] == 2
        assert data["written_reviews"] == 2 and data["avg_hire_rate"] == 40
        assert dict(data["countries"])["Canada"] == 2
        assert [p["count"] for p in data["per_day"]] == [2, 0, 1]
        assert data["release_checks"]["no_freelancer_reviews"] == 1
        ranged = client.get("/api/analytics", params={"start": "2026-10-02"}).json()
        assert ranged["total"] == 1
        rows = client.get("/api/jobs").json()
        assert {r["id"]: r["release_check"] for r in rows}["~2"] == "no_freelancer_reviews"


def test_discovery_skips_exactly_dated_cards_outside_window(tmp_path):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from types import SimpleNamespace
    from server.db import Database
    from server.pipeline import Pipeline
    config = replace(Settings(), data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'd.db'}")
    config.prepare()
    db = Database(config.database_url)
    db.init()
    tz = ZoneInfo("Asia/Kolkata")
    # Pretend it is 17:00 on 2026-10-26 IST; the window is yesterday (2026-10-25).
    fixed = datetime(2026, 10, 26, 17, 0, tzinfo=tz)
    import server.browser as browser
    real = browser.parse_upwork_date
    browser.parse_upwork_date = lambda raw: real(raw, fixed)
    try:
        cards = [{"job_id": f"~{i}", "job_url": f"https://www.upwork.com/jobs/~{i}", "posted_time": label}
                 for i, label in enumerate(["Posted 3 hours ago", "Posted 20 hours ago", "Posted yesterday", "Posted 5 minutes ago"])]
        rid = db.create_run("2026-10-25", "2026-10-25", "Asia/Kolkata")
        Pipeline(config, db).discover_page(rid, SimpleNamespace(search=lambda *_: cards))
    finally:
        browser.parse_upwork_date = real
    with db.engine.connect() as c:
        from sqlalchemy import select
        from server.db import queue
        queued = {r[0] for r in c.execute(select(queue.c.job_id))}
    # 3h and 5min ago are today; 20h ago is 21:00 yesterday (kept); coarse "yesterday" keeps its margin.
    assert queued == {"~1", "~2"}


def test_utc_window_uses_exact_day_labels(tmp_path):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from sqlalchemy import select
    from server.db import Database, queue
    from server.pipeline import Pipeline
    import server.browser as browser
    config = replace(Settings(), data_dir=tmp_path, database_url=f"sqlite:///{tmp_path / 'u.db'}")
    config.prepare()
    db = Database(config.database_url)
    db.init()
    # 11:30 UTC on 2026-10-26; window is the UTC day 2026-10-25.
    fixed = datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc)
    real = browser.parse_upwork_date
    browser.parse_upwork_date = lambda raw: real(raw, fixed)
    labels = ["Posted 3 hours ago", "Posted 20 hours ago", "Posted yesterday", "Posted 2 days ago", "Posted 3 days ago"]
    cards = [{"job_id": f"~{i}", "job_url": f"https://www.upwork.com/jobs/~{i}", "posted_time": label} for i, label in enumerate(labels)]
    try:
        rid = db.create_run("2026-10-25", "2026-10-25", "UTC")
        Pipeline(config, db).discover_page(rid, SimpleNamespace(search=lambda *_: cards))
    finally:
        browser.parse_upwork_date = real
    with db.engine.connect() as c:
        queued = {r[0] for r in c.execute(select(queue.c.job_id))}
    # 3h ago is 08:30 today; 2 and 3 days ago are 24-Oct and 23-Oct. 20h ago (15:30 on 25-Oct) and "yesterday" are in.
    assert queued == {"~1", "~2"}
    assert db.get_run(rid)["discovery_done"] == 0  # a mixed page is not yet fully older than the window


def test_jobs_list_puts_latest_saved_first_and_flags_qualified(config):
    app = create_app(config)
    with TestClient(app) as client:
        stamp = now()
        rows = [job("~old", "2026-10-25", "India", "$1K total spent", "10%"),
                job("~new", "2026-10-25", "India", "$1K total spent", "10%"),
                job("~yesterday", "2026-10-24", "India", "$1K total spent", "10%"),
                job("~noreview", "2026-10-25", "India", "$1K total spent", "10%", with_review=False)]
        for i, row in enumerate(rows):
            row["first_seen"] = stamp + i  # later index = saved later
        rows[0]["data"]["history_expansion_complete"] = False  # incomplete history still qualifies
        with app.state.db.engine.begin() as c:
            c.execute(insert(jobs), rows)
        sign_in(client)
        listed = client.get("/api/jobs").json()
        assert [r["id"] for r in listed] == ["~noreview", "~new", "~old", "~yesterday"]
        checks = {r["id"]: r["release_check"] for r in listed}
        assert checks == {"~noreview": "no_freelancer_reviews", "~new": "ready", "~old": "ready", "~yesterday": "ready"}


def test_saving_speed_per_minute(config):
    from server.analytics import speed
    app = create_app(config)
    base = 1_800_000_000 - (1_800_000_000 % 60)  # a minute boundary; "now" is 30s into minute m0
    with TestClient(app) as client:
        rows = []
        # minute -3: 2 jobs; minute -1: 1 job; current minute: 3 jobs (one without a review, so not qualified)
        for jid, offset, review in [("~a", -180, True), ("~b", -170, True), ("~c", -60, True),
                                    ("~d", 5, True), ("~e", 10, True), ("~f", 20, False)]:
            row = job(jid, "2026-10-25", "India", "$1K total spent", "10%", with_review=review)
            row["last_seen"] = base + offset
            rows.append(row)
        old = job("~old", "2026-10-25", "India", "$1K total spent", "10%")
        old["last_seen"] = base - 7200  # outside a 60-minute window
        rows.append(old)
        with app.state.db.engine.begin() as c:
            c.execute(insert(jobs), rows)
        result = speed(app.state.db, 60, reference=base + 30)
        per = {p["t"]: p for p in result["per_minute"]}
        assert len(result["per_minute"]) == 60 and result["per_minute"][-1]["t"] == base
        assert per[base - 180]["jobs"] == 2 and per[base - 60]["jobs"] == 1 and per[base - 120]["jobs"] == 0
        assert result["current_minute"] == {"t": base, "jobs": 3, "reviews": 2, "qualified": 2}
        assert result["total_jobs"] == 6 and result["total_reviews"] == 5
        # Rates ignore the unfinished current minute: 3 jobs over the last 5 finished minutes.
        assert result["jobs_per_min"][5] == 0.6 and result["peak"] == 2
        sign_in(client)
        assert client.get("/api/speed", params={"minutes": 15}).json()["per_minute"][-1]["t"] > 0
        assert len(client.get("/api/speed", params={"minutes": 15}).json()["per_minute"]) == 15


def _card(jid):
    return {"job_id": jid, "job_url": f"https://www.upwork.com/jobs/{jid}", "posted_time": "Posted yesterday"}


def test_filtered_discovery_hides_saved_jobs_that_do_not_match(config):
    from datetime import datetime, timezone
    from types import SimpleNamespace
    from server.db import Database
    from server.pipeline import Pipeline
    import server.browser as browser
    db = Database(config.database_url)
    db.init()
    with db.engine.begin() as c:
        c.execute(insert(jobs), [job("~inside", "2026-10-25", "Canada", "$1K total spent", "10%"),
                                 job("~wrongcountry", "2026-10-25", "Pakistan", "$1K total spent", "10%"),
                                 job("~otherday", "2026-10-20", "Pakistan", "$1K total spent", "10%")])
    rid = db.create_run("2026-10-25", "2026-10-25", "UTC")
    fixed = datetime(2026, 10, 26, 11, 30, tzinfo=timezone.utc)
    real = browser.parse_upwork_date
    browser.parse_upwork_date = lambda raw: real(raw, fixed)
    try:
        pipeline = Pipeline(config, db)
        # The filtered search lists only ~inside on page 1; page 2 is entirely older, which completes discovery.
        pages = iter([[_card("~inside")], [dict(_card("~x"), posted_time="Posted 5 days ago")]])
        pipeline.discover_page(rid, SimpleNamespace(search=lambda *_: next(pages)))
        pipeline.discover_page(rid, SimpleNamespace(search=lambda *_: next(pages)))
    finally:
        browser.parse_upwork_date = real
    assert db.get_run(rid)["discovery_done"] == 1
    app = create_app(config)
    with TestClient(app) as client:
        sign_in(client)
        listed = {r["id"] for r in client.get("/api/jobs").json()}
        assert listed == {"~inside", "~otherday"}  # the wrong-country job is hidden; jobs outside the window are untouched
        assert client.get("/api/analytics").json()["total"] == 2
    with db.engine.connect() as c:
        from sqlalchemy import select
        assert c.execute(select(jobs.c.id).where(jobs.c.id == "~wrongcountry")).first()  # hidden, not deleted
    db.engine.dispose()


def test_report_upload_treats_unknown_message_id_as_not_sent(config, tmp_path, monkeypatch):
    """Google returns 403 (not 404) when looking up a message ID that was never created; the report must still be sent."""
    import httplib2
    from googleapiclient.errors import HttpError
    from types import SimpleNamespace
    from server.notifications import upload_report
    token = tmp_path / "token.json"
    token.write_text("{}")
    sent = {}

    class Call:
        def __init__(self, fn): self.fn = fn
        def execute(self): return self.fn()

    def not_found():
        raise HttpError(httplib2.Response({"status": 403}), b'{"error": {"message": "does not exist"}}')

    class Messages:
        def get(self, **_): return Call(not_found)
        def create(self, **kw):
            sent.update(kw)
            return Call(lambda: {"name": "spaces/X/messages/1"})

    service = SimpleNamespace(
        spaces=lambda: SimpleNamespace(messages=lambda: Messages()),
        media=lambda: SimpleNamespace(upload=lambda **_: Call(lambda: {"attachmentDataRef": {"resourceName": "r"}})))
    monkeypatch.setattr("google.oauth2.credentials.Credentials.from_authorized_user_file",
                        lambda *a, **k: SimpleNamespace(expired=False, refresh_token=None))
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *a, **k: service)
    report = tmp_path / "report.html"
    report.write_text("<html></html>")
    settings = replace(config, chat_space="spaces/X", token_file=str(token))
    upload_report(settings, {"id": "abcdef0123456789xx", "start_date": "2026-10-25", "end_date": "2026-10-25", "status": "completed"}, report)
    assert sent["parent"] == "spaces/X" and sent["body"]["attachment"] == [{"attachmentDataRef": {"resourceName": "r"}}]
