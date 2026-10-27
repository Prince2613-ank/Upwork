import pytest

from server.browser import BrowserIssue, BrowserSession
from tests.test_browser_flow import browser
from tests.test_production_flow import card
from tests.test_unavailable_jobs import PRIVATE


@pytest.mark.parametrize('status,delayed', [(200, False), (403, False), (200, True)])
def test_private_job_page_is_detected_in_browser(browser, status, delayed):
    context = browser.new_context()
    page = context.new_page()
    if delayed:
        html = '''<html><head><title>undefined</title></head><body>
          <script>setTimeout(()=>{document.body.innerHTML=
          '<h1>Access denied</h1><p>This job is private. Only freelancers invited by client can view this job.</p>';
          },250);</script></body></html>'''
    else:
        html = '<html><head><title>undefined</title></head><body><h1>Access denied</h1><p>' + PRIVATE + '</p></body></html>'
    page.route('https://www.upwork.com/**', lambda route: route.fulfill(status=status, content_type='text/html', body=html))
    session = BrowserSession('unused')
    session.page, session.context = page, context
    try:
        with pytest.raises(BrowserIssue) as issue:
            session.detail(card())
        assert issue.value.kind == 'unavailable'
    finally:
        context.close()
