"""Browser integration checks with synthetic Upwork pages; never contacts Upwork."""
import json
import os
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from urllib.request import urlopen

import pytest
from playwright.sync_api import sync_playwright

from server.browser import BrowserSession
from server.config import Settings
from server.db import Database, runs
from server.pipeline import Pipeline
from server.quality import release_candidate
from tests.test_production_flow import PASSWORD, card, data, save_result


@pytest.fixture
def browser():
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(channel=os.getenv("BROWSER_TEST_CHANNEL", "chromium"), headless=True)
        except Exception:
            if os.getenv("RUN_BROWSER_TESTS") == "1":
                raise
            pytest.skip("Install Chromium and set RUN_BROWSER_TESTS=1 for browser integration checks")
        yield browser
        browser.close()


def history_fixture(incomplete=False):
    item = lambda title, feedback: f'''<div class="item" data-cy="job"><h4><a href="/jobs/~old123">{title}</a></h4>
      <div data-test="contract-date">2019</div><div class="payment-info">Fixed-price: $200.00</div>
      <div class="freelancer-info"><a href="/freelancers/~dev">Developer</a></div>
      <div class="main"><div><span id="air3-truncation-{title}">{feedback}</span></div>
      <div>To freelancer: Developer <span id="air3-truncation-client-{title}">CLIENT_TO_FREELANCER_MUST_NOT_APPEAR</span></div></div></div>'''
    first = item("ContractOne", 'Clear requirements...<button id="expand">more</button>')
    second = item("ContractTwo", "The client communicated clearly and paid promptly throughout the project.")
    return f'''<!doctype html><html><head><title>Example project</title></head><body><main>
      <h1>Example project</h1><div data-test="job-description-text">A complete description of a Python automation project and all requested deliverables.</div>
      <div data-test="client-history"><h3>Client's recent history (2)</h3><div id="contracts">{first}</div>
      <button id="next" aria-label="Next page" {'disabled' if incomplete else ''}>Next</button></div></main>
      <script id="__NUXT_DATA__" type="application/json">[{{"publishTime":1}},"2020-01-02T06:00:00+00:00"]</script>
      <script>document.querySelector('#expand').onclick=function(){{this.parentNode.firstChild.textContent='The client gave complete requirements and paid promptly for every delivery.';this.textContent='less';}};
      document.querySelector('#next').onclick=function(){{document.querySelector('#contracts').innerHTML={json.dumps(second)};this.disabled=true;}};</script>
      </body></html>'''


@pytest.mark.parametrize("incomplete", [False, True])
def test_history_pagination_and_review_direction(browser, incomplete):
    context = browser.new_context()
    page = context.new_page()
    page.route("https://www.upwork.com/**", lambda route:route.fulfill(status=200,content_type="text/html",body=history_fixture(incomplete)))
    session = BrowserSession("unused")
    session.page, session.context = page, context
    started=time.perf_counter()
    extracted, raw = session.detail(card())
    assert time.perf_counter()-started<8  # Equal-sized history pages must not burn the 10s growth timeout.
    assert "CLIENT_TO_FREELANCER_MUST_NOT_APPEAR" not in json.dumps(extracted["client_recent_history"])
    assert extracted["client_recent_history"][0]["feedback_full"]
    assert extracted["history_expansion_complete"] is (not incomplete)
    if not incomplete:
        assert len(extracted["client_recent_history"]) == 2
    # A job with at least one written review qualifies even when later history pages could not be loaded.
    assert release_candidate(extracted)[1] == "ready"
    context.close()


def test_late_h5_history_does_not_wait_for_missing_data_attribute(browser):
    from bs4 import BeautifulSoup
    markup=BeautifulSoup(history_fixture().replace('data-test="client-history"','class="air3-card"')
                         .replace('<h3>','<h5>').replace('</h3>','</h5>'),'html.parser')
    main=str(markup.main)
    script=markup.find_all('script')[-1].string
    html=f'<html><head><title>Example</title></head><body><h1>Example project</h1><script>setTimeout(()=>{{document.body.innerHTML={json.dumps(main)};{script}}},350);</script></body></html>'
    context=browser.new_context();page=context.new_page()
    page.route('https://www.upwork.com/**',lambda route:route.fulfill(status=200,content_type='text/html',body=html))
    session=BrowserSession('unused');session.page,session.context=page,context
    started=time.perf_counter();extracted,_=session.detail(card())
    assert time.perf_counter()-started<8
    assert len(extracted['client_recent_history'])==2
    assert extracted['history_expansion_complete'] is True
    context.close()


@pytest.fixture
def preview(tmp_path, free_tcp_port):
    env = dict(os.environ, DATABASE_URL=f"sqlite:///{tmp_path / 'app.db'}", PIPELINE_DATA_DIR=str(tmp_path),
        DASHBOARD_USER="admin", DASHBOARD_PASSWORD=PASSWORD, DASHBOARD_PASSWORD_SCRYPT="", SESSION_COOKIE_SECURE="false",
        PUBLIC_URL=f"http://127.0.0.1:{free_tcp_port}", GOOGLE_CHAT_WEBHOOK="", GOOGLE_CHAT_SPACE="")
    log_path = tmp_path / "preview.log"
    with log_path.open("w",encoding="utf-8") as log:
        process = subprocess.Popen([sys.executable,"-m","uvicorn","server.app:app","--host","127.0.0.1","--port",str(free_tcp_port)],env=env,stdout=log,stderr=log)
        url = env["PUBLIC_URL"]
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail(log_path.read_text(encoding="utf-8"))
                try:
                    with urlopen(url+"/healthz",timeout=1) as response:
                        if response.status==200:
                            break
                except Exception:
                    time.sleep(.1)
            else:
                pytest.fail("Preview server did not become healthy")
            yield url, replace(Settings(),database_url=env["DATABASE_URL"],data_dir=tmp_path,webhook="",chat_space="")
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def test_login_dates_live_feed_and_one_filtered_download(browser, preview):
    url, settings = preview
    context = browser.new_context(viewport={"width":1440,"height":1000},accept_downloads=True)
    page = context.new_page()
    errors=[]
    page.on("pageerror",lambda error:errors.append(str(error)))
    page.goto(url)
    assert page.url.endswith("/login")
    page.screenshot(path=str(settings.data_dir / "login.png"),full_page=True)
    page.locator('[name="username"]').fill("admin")
    page.locator('[name="password"]').fill(PASSWORD)
    page.get_by_role("button",name="Sign in").click()
    page.wait_for_function("document.querySelector('#connection').dataset.state==='online'")
    page.get_by_role("tab",name="Collection").click()
    page.locator('#launch [name="start_date"]').fill("2020-01-02")
    page.locator('#launch [name="end_date"]').fill("2020-01-02")
    page.get_by_role("button",name="Start two workers").click()
    page.locator("#summary").filter(has_text="queued").wait_for()
    rid = context.request.get(url+"/api/status").json()["runs"][0]["id"]
    db = Database(settings.database_url)
    db.change(rid,status="running",discovery_done=1)
    valid = data()
    missing = data("~02222")
    missing["job"].update(description="")
    missing["job_title"]="MUST_EXCLUDE_MISSING_DESCRIPTION"
    empty = data("~02333")
    empty.update(client_recent_history=[],job_title="MUST_EXCLUDE_ZERO_REVIEWS")
    for record in (valid,missing,empty):
        save_result(db,rid,record)
    Pipeline(settings,db).finish_ready()
    page.locator("#live-feed").filter(has_text="Example project").wait_for(timeout=15000)
    page.get_by_role("tab",name="Files",exact=True).click()
    page.get_by_role("link",name="Download single HTML report").wait_for(timeout=15000)
    page.screenshot(path=str(settings.data_dir / "dashboard.png"),full_page=True)
    with page.expect_download() as download_info:
        page.get_by_role("link",name="Download single HTML report").click()
    target=settings.data_dir / "downloaded-report.html"
    download_info.value.save_as(target)
    report=target.read_text(encoding="utf-8")
    assert "The client gave clear requirements" in report
    assert "MUST_EXCLUDE" not in report
    assert page.get_by_role("link",name="Download single HTML report").count()==1
    page.get_by_role("button",name="Sign out").click()
    page.wait_for_url(url+"/login")
    assert context.request.get(url+"/api/status").status==401
    assert not errors
    context.close()
    db.engine.dispose()
