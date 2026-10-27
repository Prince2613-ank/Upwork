import time
from types import SimpleNamespace

import pytest

from server.pipeline import Pipeline
from tests.test_production_flow import settings, db, data, card, new_run


def test_worker_reuses_connection_across_jobs_and_disconnects_on_pause(db,settings,monkeypatch):
    rid=new_run(db);db.change(rid,status='running',discovery_done=1)
    db.enqueue(rid,[card('~reuse1'),card('~reuse2')])
    connections=[]
    class Session:
        def __init__(self,*_):pass
        def __enter__(self):connections.append('connect');return self
        def __exit__(self,*_):connections.append('disconnect')
        def detail(self,candidate,*_):return data(candidate['job_id']),'<html>Complete description</html>'
    class StopWorker(BaseException):pass
    pipeline=Pipeline(settings,db)
    process=pipeline.process_item
    def process_and_pause(*args):
        process(*args)
        if db.counts(rid).get('done')==2:db.change(rid,status='paused')
    pipeline.process_item=process_and_pause
    def sleep(seconds):
        pipeline.last_attempt['B']=0
        if seconds==1 and db.counts(rid).get('done')==2:raise StopWorker()
    monkeypatch.setattr('server.pipeline.BrowserSession',Session)
    monkeypatch.setattr('server.pipeline.time',SimpleNamespace(monotonic=time.monotonic,sleep=sleep))
    with pytest.raises(StopWorker):pipeline.worker('B')
    assert connections==['connect','disconnect']
    assert db.counts(rid)=={'done':2}
    assert db.get_run(rid)['status']=='paused'
