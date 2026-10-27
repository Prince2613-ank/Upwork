import json
from pathlib import Path

import pytest
from sqlalchemy import insert, select, update

from deploy.configure import configure, validate
from server.db import Database, control, events, jobs, queue, runs, sessions
from server.transfer import export_sqlite, import_snapshot
from tests.test_server_pipeline import db
from tests.test_production_flow import card, data


def test_modern_snapshot_preserves_rows_and_resumes_safely(db, tmp_path):
    source = Database('sqlite:///' + (tmp_path / 'source.db').as_posix(), timezone='Asia/Kolkata')
    source.init()
    assert source.settings()['timezone'] == 'Asia/Kolkata'
    rid = source.create_run('2020-01-01', '2020-01-01', 'Asia/Kolkata')
    source.change(rid, status='running', report=rid + '/upwork_Wednesday_scarpe_2020-01-01.html')
    source.enqueue(rid, [card('~saved'), card('~inflight')])
    item = source.claim(rid, 'A')
    source.save(item, data('~saved'), '2020-01-01', 'digest.html.gz')
    source.claim(rid, 'B')
    source.event(rid, 'job_saved', 'Saved example')
    with source.engine.begin() as c:
        c.execute(insert(sessions).values(token_hash='do-not-transfer', csrf_hash='secret'))
        options = source.settings(c)
        options.update(enabled=True, deliver_to_chat=True)
        c.execute(update(control).values(settings=options, remote_control=1))
    output = tmp_path / 'snapshot.json'
    counts = export_sqlite(tmp_path / 'source.db', output)
    assert 'do-not-transfer' not in output.read_text()
    assert counts == import_snapshot(db, output)
    assert db.counts(rid) == {'done': 1, 'pending': 1}
    assert db.get_run(rid)['status'] == 'paused'
    assert db.get_run(rid)['report'] == source.get_run(rid)['report']
    assert not db.settings()['enabled'] and not db.settings()['deliver_to_chat']
    assert db.settings()['timezone'] == 'Asia/Kolkata'
    assert source.get_run(rid)['status'] == 'running'
    assert source.counts(rid)['running'] == 1
    assert db.quality_counts(rid)['ready'] == 1
    # Imported integer IDs must not collide with the next PostgreSQL sequence value.
    db.event(rid, 'verification', 'New server event')
    db.enqueue(rid, [card('~new')])
    assert db.counts(rid)['pending'] == 2
    with pytest.raises(ValueError, match='not empty'):
        import_snapshot(db, output)
    source.engine.dispose()


def test_server_configure_reuses_credentials_and_removes_old_fields(tmp_path):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / '.env.server.example').write_text((root / '.env.server.example').read_text())
    (tmp_path / '.env.server').write_text('DASHBOARD_PASSWORD_HASH=obsolete\nPOSTGRES_PASSWORD=replace-me\n')
    (tmp_path / 'token.json').write_text('{"test":"credential"}')
    (tmp_path / '.env.local').write_text("DASHBOARD_PASSWORD_SCRYPT='scrypt$32768$8$3$salt$hash'\nGOOGLE_CHAT_WEBHOOK=https://chat.test/hook\nGOOGLE_CHAT_SPACE=spaces/test\nGOOGLE_CHAT_TOKEN_FILE=token.json\n")
    assert configure(tmp_path, True, 'jobs.company.test') == []
    from dotenv import dotenv_values
    values = dotenv_values(tmp_path / '.env.server', interpolate=False)
    assert 'DASHBOARD_PASSWORD_HASH' not in values and 'DASHBOARD_PASSWORD' not in values
    assert values['DASHBOARD_PASSWORD_SCRYPT'] == 'scrypt$32768$8$3$salt$hash'
    assert len(values['POSTGRES_PASSWORD']) == 64
    assert (tmp_path / 'deploy/secrets/google-chat-token.json').is_file()
    assert validate(values, tmp_path / 'deploy/secrets/google-chat-token.json') == []
    configure(tmp_path, True)
    assert dotenv_values(tmp_path / '.env.server')['POSTGRES_PASSWORD'] == values['POSTGRES_PASSWORD']
