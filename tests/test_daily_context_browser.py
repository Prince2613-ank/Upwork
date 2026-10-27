from playwright.sync_api import expect
from sqlalchemy import insert

from tests.test_browser_flow import browser, preview
from tests.test_dashboard_ui import job
from tests.test_production_flow import PASSWORD, data, save_result
from server.db import Database


def test_overview_follows_current_run_and_daily_rollover(browser, preview):
    url, settings = preview
    db = Database(settings.database_url)
    db.init()
    with db.engine.begin() as c:
        from server.db import jobs
        c.execute(insert(jobs).values(**job('historical', '2020-01-01', 'Canada', '$5K', '50%')))
    context = browser.new_context()
    page = context.new_page()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.goto(url)
    page.locator('[name="username"]').fill('admin')
    page.locator('[name="password"]').fill(PASSWORD)
    page.get_by_role('button', name='Sign in').click()
    expect(page.locator('#analytics-context')).to_contain_text('no collection started today')
    expect(page.locator('#kpis .kpi').first.locator('strong')).to_have_text('0')
    rid = db.create_run('2020-01-02', '2020-01-02', 'Asia/Kolkata')
    save_result(db, rid, data())
    page.evaluate('refresh()')
    expect(page.locator('#analytics-context')).to_contain_text('2020-01-02')
    expect(page.locator('#kpis .kpi').first.locator('strong')).to_have_text('1')
    page.get_by_role('tab', name='Collection', exact=True).click()
    expect(page.locator('#jobs details')).to_have_count(1)
    # A completed run from a prior calendar day must disappear on the next poll.
    db.change(rid, status='completed', created_at=1)
    page.evaluate('refresh()')
    expect(page.locator('#jobs details')).to_have_count(0)
    page.get_by_role('tab', name='Overview', exact=True).click()
    expect(page.locator('#kpis .kpi').first.locator('strong')).to_have_text('0')
    assert not errors
    context.close()
    db.engine.dispose()


def test_expanded_page_controls_and_status_colors(browser, preview):
    url, settings = preview
    db = Database(settings.database_url)
    db.init()
    rid = db.create_run('2020-01-02', '2020-01-02', 'Asia/Kolkata')
    db.change(rid, status='running')
    save_result(db,rid,data())
    context = browser.new_context(viewport={'width':1440,'height':1000})
    page = context.new_page()
    errors=[]
    page.on('pageerror', lambda error:errors.append(str(error)))
    page.goto(url)
    page.locator('[name="username"]').fill('admin')
    page.locator('[name="password"]').fill(PASSWORD)
    page.get_by_role('button',name='Sign in').click()
    expect(page.locator('#controlled-run')).to_contain_text('running')
    assert page.locator('#controlled-run > span').count()==1
    assert page.locator('#controlled-run').get_attribute('title') is None
    assert page.locator('.navbar-controls, .navbar-dropdown').count()==0
    assert page.locator('main h1, main [data-clear-view], .connection-indicator').count()==0
    assert page.locator('#files-filter').count()==0
    expect(page.locator('.header-actions [data-clear-view]')).to_be_visible()
    assert page.locator('.topbar').bounding_box()['height']<90
    assert page.locator('#range, #speed-window').count()==0
    expect(page.locator('.speed-period')).to_have_text('Last 15 minutes')
    expect(page.locator('.header-actions [data-clear-view]')).to_have_text('Clean')
    assert page.locator('.topbar > strong').count()==0
    assert page.locator('.header-actions [data-clear-view]').evaluate('el=>getComputedStyle(el).borderStyle')=='solid'
    assert page.locator('.header-actions [data-clear-view]').bounding_box()['height']>=30
    with page.expect_request('**/api/speed?*') as speed_request:
        page.evaluate('loadSpeed()')
    assert 'minutes=15' in speed_request.value.url
    assert page.locator('.run-state').evaluate('el=>getComputedStyle(el).color')=='rgb(36, 91, 212)'
    page.locator('#control-actions').get_by_role('button',name='Pause',exact=True).click()
    expect(page.locator('#controlled-run')).to_contain_text('paused')
    assert page.locator('.run-state').evaluate('el=>getComputedStyle(el).backgroundColor')=='rgb(255, 237, 172)'
    db.change(rid,status='attention')
    page.evaluate('refresh()')
    expect(page.locator('#controlled-run')).to_contain_text('attention')
    assert page.locator('.run-state').evaluate('el=>getComputedStyle(el).color')=='rgb(179, 38, 30)'
    for tab,form in [('Collection','#launch'),('Browsers',None),('Files',None),('Schedule','#schedule')]:
        page.get_by_role('tab',name=tab,exact=True).click()
        if form: expect(page.locator(form)).to_be_visible()
        assert page.locator('main').bounding_box()['width']>=1440-1
        if tab=='Browsers':
            if page.locator('#toggle-browser-windows').is_visible():
                expect(page.locator('#toggle-browser-windows')).to_have_text('Show both browsers')
                page.locator('#toggle-browser-windows').click()
                expect(page.locator('#toggle-browser-windows')).to_have_text('Hide both browsers')
                assert db.settings()['browser_windows_visible'] is True
                assert db.get_run(rid)['status']=='attention'
                page.locator('#toggle-browser-windows').click()
                expect(page.locator('#toggle-browser-windows')).to_have_text('Show both browsers')
            expect(page.locator('#worker-speed')).to_be_visible()
            page.locator('#worker-speed-rate').fill('12')
            page.get_by_role('button',name='Apply speed',exact=True).click()
            expect(page.locator('#worker-speed-current')).to_contain_text('12/min each')
            assert db.settings()['jobs_per_minute']==12
            expect(page.locator('#schedule [name=jobs_per_minute]')).to_have_value('12')
            # Live polling must not overwrite a speed the user is still editing.
            page.locator('#worker-speed-rate').fill('8')
            page.evaluate('refresh()')
            expect(page.locator('#worker-speed-rate')).to_have_value('8')
            assert db.settings()['jobs_per_minute']==12
        if tab=='Collection':
            expect(page.locator('#filter')).to_be_visible()
            assert page.locator('[data-tab=jobs], #events').count()==0
            assert page.locator('#tab-collection #jobs').count()==1
            assert page.locator('#tab-browsers #runs').count()==1
            assert page.locator('#jobs-sync, #jobs-count, #clear-filter').count()==0
            expect(page.locator('#jobs details')).to_have_count(1)
            save_result(db,rid,data('~new'))
            page.evaluate('loadJobs()')
            badges=page.locator('#jobs details[data-id="~new"] .job-badges')
            expect(badges.locator('.fresh')).to_have_text('New')
            expect(badges.locator('.qualification')).to_have_text('Qualified')
            assert badges.locator('.qualification').bounding_box()['width']<110
            assert badges.locator('.qualification').bounding_box()['y']>badges.locator('.fresh').bounding_box()['y']
            page.screenshot(path=str(settings.data_dir/'jobs-compact.png'))
    page.get_by_role('button',name='Save settings').click()
    expect(page.locator('#message')).to_have_text('Settings saved.')
    page.get_by_role('tab',name='Collection',exact=True).click()
    page.screenshot(path=str(settings.data_dir/'page-desktop.png'))
    page.set_viewport_size({'width':390,'height':844})
    for tab in ['Overview','Collection','Files','Browsers','Schedule']:
        page.get_by_role('tab',name=tab,exact=True).click()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
    page.screenshot(path=str(settings.data_dir/'page-mobile.png'))
    assert not errors
    context.close();db.engine.dispose()


def test_clean_removes_saved_jobs_but_preserves_files(browser,preview):
    from server.reports import build_report
    url,settings=preview
    db=Database(settings.database_url);db.init()
    rid=db.create_run('2020-01-02','2020-01-02','Asia/Kolkata')
    save_result(db,rid,data())
    filename,_=build_report(db,settings,db.get_run(rid))
    db.change(rid,status='running',report=filename)
    context=browser.new_context(accept_downloads=True)
    page=context.new_page();page.goto(url)
    page.locator('[name="username"]').fill('admin')
    page.locator('[name="password"]').fill(PASSWORD)
    page.get_by_role('button',name='Sign in').click()
    expect(page.locator('#kpis .kpi').first.locator('strong')).to_have_text('1')
    page.get_by_role('tab',name='Collection',exact=True).click()
    expect(page.locator('#jobs details')).to_have_count(1)
    page.locator('.header-actions [data-clear-view]').click()
    expect(page.get_by_role('dialog')).to_be_visible()
    page.get_by_role('dialog').get_by_role('button',name='Clean jobs',exact=True).click()
    expect(page.locator('#message')).to_contain_text('Stop the existing collection')
    assert db.counts(rid)['done']==1
    expect(page.locator('#message')).not_to_be_visible(timeout=6500)
    page.locator('#control-actions').get_by_role('button',name='Stop',exact=True).click()
    expect(page.locator('#controlled-run')).to_contain_text('stopped')
    page.locator('.header-actions [data-clear-view]').click()
    page.get_by_role('dialog').get_by_role('button',name='Cancel',exact=True).click()
    expect(page.get_by_role('dialog')).not_to_be_visible()
    assert db.counts(rid)['done']==1
    assert db.get_run(rid)['status']=='stopped'
    page.locator('.header-actions [data-clear-view]').click()
    page.get_by_role('dialog').get_by_role('button',name='Clean jobs',exact=True).click()
    expect(page.locator('#message')).to_contain_text('1 jobs removed')
    expect(page.locator('#jobs details')).to_have_count(0)
    page.reload()
    expect(page.locator('#jobs details')).to_have_count(0)
    assert db.get_run(rid)['status']=='cleaned'
    page.get_by_role('tab',name='Files',exact=True).click()
    expect(page.locator('#files-list .file-card')).to_have_count(1)
    expect(page.locator('#files-list')).to_contain_text('upwork_')
    expect(page.locator('#files-list')).to_contain_text('_scrape_')
    with page.expect_download() as downloaded:
        page.locator('#files-list').get_by_role('link',name='Download HTML').click()
    assert downloaded.value.suggested_filename==filename.split('/')[-1]
    assert page.locator('#files-search, #refresh-files').count()==0
    context.close();db.engine.dispose()
