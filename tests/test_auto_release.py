from pathlib import Path

from sqlalchemy import select, update

from server.db import control, events, queue
from server.pipeline import Pipeline
from server.reports import report_name
from tests.test_production_flow import settings, db, client, card, data, save_result, new_run, sign_in


def enable_chat(db):
    with db.engine.begin() as c:
        config=db.settings(c)
        config['deliver_to_chat']=True
        c.execute(update(control).values(settings=config))


def test_window_finishes_then_auto_releases_and_uploads_once(db,settings,monkeypatch):
    enable_chat(db)
    rid=new_run(db)
    db.change(rid,status='running')
    save_result(db,rid,data())
    excluded=data('~empty')
    excluded['client_recent_history']=[]
    excluded['job_title']='EXCLUDE_NO_REVIEWS'
    save_result(db,rid,excluded)
    db.enqueue(rid,[card('~pending')])
    pipeline=Pipeline(settings,db)
    uploaded=[]
    monkeypatch.setattr('server.pipeline.upload_report',lambda config,run,path:uploaded.append((run['id'],path.name,path.read_text(encoding='utf-8'))))
    pipeline.finish_ready()
    assert db.get_run(rid)['report']==''  # Discovery has not finished.
    db.change(rid,discovery_done=1)
    pipeline.finish_ready()
    assert db.get_run(rid)['report']==''  # Pending jobs must finish first.
    with db.engine.begin() as c:
        c.execute(update(queue).where(queue.c.run_id==rid,queue.c.job_id=='~pending').values(status='unavailable'))
    pipeline.finish_ready()
    run=db.get_run(rid)
    assert run['status']=='completed' and run['delivery']=='pending'
    assert Path(run['report']).name==report_name(run)
    assert Path(run['report']).name.startswith('upwork_')
    pipeline.deliver()
    assert db.get_run(rid)['delivery']=='sent'
    assert len(uploaded)==1 and uploaded[0][1]==report_name(run)
    assert 'EXCLUDE_NO_REVIEWS' not in uploaded[0][2]
    assert 'The client gave clear requirements' in uploaded[0][2]
    pipeline.finish_ready();pipeline.deliver()
    assert len(uploaded)==1
    with db.engine.connect() as c:
        assert c.execute(select(events.c.id).where(events.c.run_id==rid,events.c.kind=='delivery_sent')).first()


def test_release_failure_retries_without_crashing_or_losing_jobs(db,settings,monkeypatch):
    rid=new_run(db)
    db.change(rid,status='running',discovery_done=1)
    save_result(db,rid,data())
    def fail(*_):raise OSError('Report storage unavailable')
    monkeypatch.setattr('server.pipeline.build_report',fail)
    pipeline=Pipeline(settings,db)
    for i in range(5):
        db.change(rid,retry_at=0)
        pipeline.finish_ready()
        run=db.get_run(rid)
        assert run['status']==('attention' if i==4 else 'running')
        assert db.counts(rid)['done']==1
        assert run['report']==''
    assert run['phase']=='release_retry'


def test_attachment_failures_retry_separately_and_keep_report(db,settings,monkeypatch):
    enable_chat(db)
    rid=new_run(db)
    db.change(rid,status='running',discovery_done=1)
    save_result(db,rid,data())
    pipeline=Pipeline(settings,db);pipeline.finish_ready()
    def fail(*_):raise TimeoutError('Chat unavailable')
    monkeypatch.setattr('server.pipeline.upload_report',fail)
    for i in range(5):
        db.change(rid,delivery_retry_at=0)
        pipeline.deliver()
        run=db.get_run(rid)
        assert run['status']=='completed'
        assert run['delivery']==('failed' if i==4 else 'retry')
        assert run['delivery_attempts']==i+1
        assert (settings.data_dir/'reports'/run['report']).is_file()


def test_disabled_chat_still_releases_html(db,settings,monkeypatch):
    rid=new_run(db)
    db.change(rid,status='running',discovery_done=1)
    save_result(db,rid,data())
    uploaded=[]
    monkeypatch.setattr('server.pipeline.upload_report',lambda *_:uploaded.append(True))
    pipeline=Pipeline(settings,db);pipeline.finish_ready();pipeline.deliver()
    run=db.get_run(rid)
    assert run['report'] and run['delivery']=='disabled' and not uploaded
