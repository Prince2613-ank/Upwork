from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import insert

from server.analytics import current_context, speed, summarize
from server.db import jobs, queue
from tests.test_dashboard_ui import config, job, sign_in
from server.app import create_app
from fastapi.testclient import TestClient


def test_context_rolls_over_at_local_midnight_and_keeps_active_run(config):
    with TestClient(create_app(config)) as client:
        db = client.app.state.db
        before = datetime(2026, 10, 26, 23, 59, tzinfo=ZoneInfo('Asia/Kolkata')).timestamp()
        after = before + 120
        rid = db.create_run('2026-10-25', '2026-10-25', 'Asia/Kolkata')
        db.change(rid, created_at=before, status='completed')
        assert current_context(db, 'Asia/Kolkata', before)['run_id'] == rid
        assert current_context(db, 'Asia/Kolkata', after)['run_id'] is None
        db.change(rid, status='running')
        assert current_context(db, 'Asia/Kolkata', after)['run_id'] == rid


def test_run_scope_excludes_historical_jobs_and_uses_fresh_snapshots(config):
    with TestClient(create_app(config)) as client:
        db = client.app.state.db
        rid = db.create_run('2026-10-25', '2026-10-25', 'Asia/Kolkata')
        old = job('old', '2026-10-25', 'Canada', '$1K', '50%')
        current = job('current', '2026-10-25', 'India', '$2K', '20%')
        snapshot = job('current', '2026-10-25', 'India', '$2K', '20%', with_review=False)['data']
        with db.engine.begin() as c:
            c.execute(insert(jobs), [old, current])
            c.execute(insert(queue).values(run_id=rid, job_id='current', status='done', result=snapshot))
        assert summarize(db)['total'] == 2
        assert summarize(db, run_id=rid)['total'] == 1
        assert summarize(db, run_id=rid)['release_ready'] == 0
        assert speed(db, run_id=rid)['total_jobs'] == 1
        assert summarize(db, run_id='__no_current_run__')['total'] == 0
        sign_in(client)
        assert client.get('/api/status').json()['display_context']['run_id'] == rid
        assert client.get('/api/analytics', params={'run_id':rid}).json()['total'] == 1
        listed = client.get('/api/jobs', params={'run_id':rid}).json()
        assert [row['id'] for row in listed] == ['current']
        assert listed[0]['release_check'] == 'no_freelancer_reviews'
        assert client.get('/api/jobs', params={'run_id':'__no_current_run__'}).json() == []
