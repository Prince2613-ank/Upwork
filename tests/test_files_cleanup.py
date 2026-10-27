from datetime import datetime, timezone

from sqlalchemy import insert, select

from server.db import jobs, queue
from server.reports import build_report, report_name
from tests.test_production_flow import settings, client, sign_in, data, save_result, card


def test_report_filename_uses_local_scrape_day():
    stamp = datetime(2026, 10, 26, 20, 0, tzinfo=timezone.utc).timestamp()
    assert report_name({'created_at': stamp, 'timezone': 'Asia/Kolkata'}) == 'upwork_Tuesday_scrape_2026-10-27.html'


def test_cleanup_removes_latest_jobs_and_snapshot_but_keeps_all_html(client, settings):
    db = client.app.state.db
    old = db.create_run('2020-01-02', '2020-01-02', 'Asia/Kolkata')
    save_result(db, old, data('~old'))
    first, _ = build_report(db, settings, db.get_run(old))
    db.change(old, status='completed', report=first)
    latest = db.create_run('2020-01-02', '2020-01-02', 'Asia/Kolkata')
    save_result(db, latest, data('~latest'))
    second, _ = build_report(db, settings, db.get_run(latest))
    db.change(latest, status='completed', report=second)
    assert first != second  # two same-day runs cannot overwrite one another
    legacy = settings.data_dir / 'reports' / 'old-report.html'
    legacy.write_text('<html>Old report</html>', encoding='utf-8')
    headers = sign_in(client)
    assert client.post('/api/data/clean-latest', json={}).status_code == 403
    result = client.post('/api/data/clean-latest', json={}, headers=headers)
    assert result.status_code == 200 and result.json()['deleted'] == 1
    assert {r['id'] for r in client.get('/api/jobs').json()} == {'~old'}
    assert db.get_run(latest)['status'] == 'cleaned'
    assert client.get('/api/status').json()['display_context']['run_id'] is None
    with db.engine.connect() as c:
        assert c.execute(select(queue.c.result).where(queue.c.run_id == latest)).scalar_one() is None
    assert client.post('/api/data/clean-latest', json={}, headers=headers).json()['deleted'] == 0
    assert client.post(f'/api/runs/{latest}/retry', json={}, headers=headers).status_code == 409
    files = client.get('/api/files').json()
    assert len(files) == 3
    for item in files:
        response = client.get(item['download_url'])
        assert response.status_code == 200
        assert item['name'] in response.headers['content-disposition']
    assert client.get(f'/api/runs/{latest}/export/html').status_code == 200
    assert client.get('/api/files/not-a-file/download').status_code == 404


def test_clean_rejects_active_or_inflight_work(client):
    headers = sign_in(client)
    db = client.app.state.db
    rid = db.create_run('2020-01-02', '2020-01-02', 'UTC')
    db.change(rid, status='paused')
    assert client.post('/api/data/clean-latest', json={}, headers=headers).status_code == 409
    db.change(rid, status='stopped')
    db.enqueue(rid, [card()])
    db.claim(rid, 'A')
    assert client.post('/api/data/clean-latest', json={}, headers=headers).status_code == 409


def test_files_are_protected_and_empty_cleanup_is_safe(client):
    assert client.get('/api/files').status_code == 401
    headers = sign_in(client)
    assert client.get('/api/files').json() == []
    assert client.post('/api/data/clean-latest', json={}, headers=headers).json()['deleted'] == 0
