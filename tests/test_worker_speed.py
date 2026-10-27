from types import SimpleNamespace

import pytest
from sqlalchemy import update

from server.db import control
from server.pipeline import Pipeline
from tests.test_production_flow import settings, client, sign_in, data, card, new_run


def test_browser_speed_setting_changes_both_real_worker_pacing(client,settings,monkeypatch):
    db=client.app.state.db
    headers=sign_in(client)
    rid=new_run(db);db.change(rid,status='running')
    db.enqueue(rid,[card('~speedA'),card('~speedB')])
    with db.engine.begin() as c:
        options=db.settings(c);options['jobs_per_minute']=1
        c.execute(update(control).values(settings=options))
    before=db.settings()
    # Six seconds since the last attempt: blocked at 1/min, eligible at 12/min.
    monkeypatch.setattr('server.pipeline.time',SimpleNamespace(monotonic=lambda:106.0))
    pipeline=Pipeline(settings,db)
    pipeline.last_attempt={'A':100.0,'B':100.0}
    calls=[]
    def detail(candidate,*_):
        calls.append(candidate['job_id'])
        return data(candidate['job_id']),'<html>Full job</html>'
    session=SimpleNamespace(detail=detail)
    pipeline.process_item(rid,'A',session);pipeline.process_item(rid,'B',session)
    assert not calls
    response=client.put('/api/collection-speed',json={'jobs_per_minute':12},headers=headers)
    assert response.status_code==200 and response.json()['combined_target']==24
    assert client.get('/api/status').json()['collection_speed']==12
    after=db.settings()
    assert {k:v for k,v in before.items() if k!='jobs_per_minute'}=={k:v for k,v in after.items() if k!='jobs_per_minute'}
    pipeline.process_item(rid,'A',session);pipeline.process_item(rid,'B',session)
    assert calls==['~speedA','~speedB'] and db.counts(rid)['done']==2
    # Lowering speed also takes effect without recreating the worker.
    db.enqueue(rid,[card('~slower')])
    pipeline.last_attempt['A']=100.0
    client.put('/api/collection-speed',json={'jobs_per_minute':1},headers=headers)
    pipeline.process_item(rid,'A',session)
    assert '~slower' not in calls


@pytest.mark.parametrize('rate',[0,21,-1,2.5,True,'12'])
def test_invalid_speed_is_rejected(client,rate):
    headers=sign_in(client)
    original=client.app.state.db.settings()['jobs_per_minute']
    assert client.put('/api/collection-speed',json={'jobs_per_minute':rate},headers=headers).status_code==422
    assert client.app.state.db.settings()['jobs_per_minute']==original


def test_speed_requires_login_and_csrf(client):
    assert client.put('/api/collection-speed',json={'jobs_per_minute':10},headers={'X-Requested-With':'pipeline-dashboard'}).status_code==401
    sign_in(client)
    assert client.put('/api/collection-speed',json={'jobs_per_minute':10},headers={'X-Requested-With':'pipeline-dashboard'}).status_code==403
