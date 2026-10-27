import os

import pytest
from sqlalchemy import select

from server.db import control
from tests.test_production_flow import settings, client, sign_in, new_run, card


@pytest.mark.skipif(os.name!='nt',reason='Local Windows window control')
def test_show_and_hide_both_does_not_pause_or_restart_collection(client):
    headers=sign_in(client);db=client.app.state.db
    rid=new_run(db);db.change(rid,status='running')
    db.enqueue(rid,[card()])
    assert client.get('/api/status').json()['browser_windows_visible'] is False
    for visible in [True,False,True]:
        result=client.put('/api/browser/visibility',json={'visible':visible},headers=headers)
        assert result.status_code==200 and result.json()['visible']==visible
        assert client.get('/api/status').json()['browser_windows_visible']==visible
        assert db.get_run(rid)['status']=='running'
        assert db.counts(rid)=={'pending':1}
    # Saving schedule settings must not silently overwrite the visibility toggle.
    config=client.get('/api/schedule').json()
    assert client.put('/api/schedule',json=config,headers=headers).status_code==200
    assert client.get('/api/status').json()['browser_windows_visible'] is True


@pytest.mark.skipif(os.name!='nt',reason='Local Windows window control')
def test_release_control_always_hides_both(client):
    headers=sign_in(client);db=client.app.state.db
    rid=new_run(db);db.change(rid,status='paused')
    assert client.post('/api/browser/take-control',json={},headers=headers).status_code==200
    assert client.get('/api/status').json()['browser_windows_visible'] is True
    client.put('/api/browser/visibility',json={'visible':True},headers=headers)
    assert client.post('/api/browser/release-control',json={},headers=headers).status_code==200
    status=client.get('/api/status').json()
    assert status['remote_control'] is False and status['browser_windows_visible'] is False
    assert db.get_run(rid)['status']=='paused'


def test_visibility_requires_csrf_and_login(client):
    assert client.put('/api/browser/visibility',json={'visible':True},headers={'X-Requested-With':'pipeline-dashboard'}).status_code==401
    sign_in(client)
    assert client.put('/api/browser/visibility',json={'visible':True},headers={'X-Requested-With':'pipeline-dashboard'}).status_code==403
