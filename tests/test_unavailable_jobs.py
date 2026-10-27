from types import SimpleNamespace

import pytest
from sqlalchemy import select

from server.browser import BrowserIssue, BrowserSession, classify
from server.db import events, queue
from server.pipeline import Pipeline
from tests.test_production_flow import settings, db, card, data, new_run


PRIVATE = 'Access denied. This job is private. Only freelancers invited by client can view this job.'


@pytest.mark.parametrize('status', [200, 403])
@pytest.mark.parametrize('text', [PRIVATE, 'This job is no longer available', 'This job has been removed'])
def test_job_specific_denials_are_unavailable(status, text):
    with pytest.raises(BrowserIssue) as issue:
        classify(status, card()['job_url'], 'undefined', text)
    assert issue.value.kind == 'unavailable'


@pytest.mark.parametrize('status,url,text,kind', [
    (403, card()['job_url'], 'Access denied', 'needs_verification'),
    (403, card()['job_url'], 'Verify you are human. ' + PRIVATE, 'needs_verification'),
    (429, card()['job_url'], PRIVATE, 'cooldown'),
    (200, card()['job_url'], 'Your account has been suspended. ' + PRIVATE, 'blocked'),
    (200, 'https://www.upwork.com/login', PRIVATE, 'needs_login'),
    (403, 'https://www.upwork.com/nx/search/jobs', PRIVATE, 'needs_verification'),
])
def test_systemic_failures_still_pause(status, url, text, kind):
    with pytest.raises(BrowserIssue) as issue:
        classify(status, url, '', text)
    assert issue.value.kind == kind


def test_private_job_skips_without_retry_and_next_job_is_saved(db, settings):
    rid = new_run(db)
    db.change(rid, status='running', discovery_done=1)
    db.enqueue(rid, [card('~private'), card('~next')])
    calls = []

    def detail(candidate, *_):
        calls.append(candidate['job_id'])
        if candidate['job_id'] == '~private':
            classify(403, candidate['job_url'], 'Access denied', PRIVATE)
        return data('~next'), '<html>valid job</html>'

    pipeline = Pipeline(settings, db)
    for _ in range(2):
        pipeline.last_attempt['A'] = 0
        pipeline.process_item(rid, 'A', SimpleNamespace(detail=detail))
    assert calls == ['~private', '~next']
    assert db.counts(rid) == {'unavailable': 1, 'done': 1}
    assert db.get_run(rid)['status'] == 'running'
    with db.engine.connect() as c:
        skipped = c.execute(select(queue).where(queue.c.job_id == '~private')).mappings().one()
        assert 'Private job' in skipped['error']
        assert c.execute(select(events.c.id).where(events.c.kind == 'job_skipped')).first()
    pipeline.finish_ready()
    assert db.get_run(rid)['status'] == 'completed'


def test_late_rendered_private_page_is_checked_before_parsing():
    # A shell can load successfully then render the private-job error while waiting for a heading.
    page = SimpleNamespace(url=card()['job_url'], title=lambda: 'undefined')
    page.locator = lambda selector: SimpleNamespace(
        first=SimpleNamespace(wait_for=lambda **_: (_ for _ in ()).throw(TimeoutError('heading missing'))),
        inner_text=lambda **_: PRIVATE)
    session = BrowserSession('unused')
    session.page = page
    session.navigate = lambda _: None
    with pytest.raises(BrowserIssue) as issue:
        session.detail(card())
    assert issue.value.kind == 'unavailable'
