from playwright.sync_api import expect

from server.db import Database
from tests.test_browser_flow import browser, preview
from tests.test_production_flow import PASSWORD, data, save_result


def test_overview_fits_screen_without_hiding_remaining_cards(browser,preview):
    url,settings=preview
    db=Database(settings.database_url);db.init()
    rid=db.create_run('2020-01-02','2020-01-02','Asia/Kolkata')
    db.change(rid,status='running')
    countries=['United States','United Kingdom','Canada','Australia','Germany','France','India','Singapore','Japan']
    for i in range(18):
        record=data('~layout'+str(i));record['client']['location']=countries[i%len(countries)]
        save_result(db,rid,record)
    context=browser.new_context(viewport={'width':1440,'height':900})
    page=context.new_page();errors=[]
    page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(url)
    page.locator('[name="username"]').fill('admin')
    page.locator('[name="password"]').fill(PASSWORD)
    page.get_by_role('button',name='Sign in').click()
    expect(page.locator('#chart-countries svg')).to_be_visible()
    assert page.locator('#chart-spend, #chart-quality, #chart-days').count()==0
    for width,height in [(1920,1080),(1440,900),(1366,768),(1280,640),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        page.evaluate('async()=>{await loadSpeed();await loadAnalytics();}')
        assert page.locator('main').bounding_box()['width']>=width-1
        speed_bounds=page.locator('.overview-speed').bounding_box()
        country_bounds=page.locator('.overview-countries').bounding_box()
        assert abs(speed_bounds['y']-country_bounds['y'])<=1
        assert speed_bounds['x']+speed_bounds['width']<=country_bounds['x']
        assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1')
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1')
        for selector in ['#kpis','#speed-kpis','#chart-speed','#chart-countries']:
            bounds=page.locator(selector).bounding_box()
            assert bounds['y']>=0 and bounds['y']+bounds['height']<=height
            assert bounds['height']>=24
        page.mouse.wheel(0,1000)
        assert page.evaluate('scrollY')==0
        if width==1366:page.screenshot(path=str(settings.data_dir/'overview-one-screen.png'))
    page.get_by_role('tab',name='Collection',exact=True).click()
    expect(page.locator('#jobs details')).to_have_count(18)
    assert page.evaluate('getComputedStyle(document.body).overflowY')!='hidden'
    for width,height in [(1440,900),(1366,768),(1280,640),(390,844)]:
        page.set_viewport_size({'width':width,'height':height})
        for tab,selector in [('Files','#tab-files'),('Browsers','#tab-browsers'),('Schedule','#tab-settings')]:
            page.get_by_role('tab',name=tab,exact=True).click()
            expect(page.locator(selector)).to_be_visible()
            assert page.evaluate('document.documentElement.scrollHeight <= innerHeight + 1'), (tab,width,height)
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth + 1'), (tab,width,height)
        page.evaluate("""()=>{
            const feed=document.querySelector('#live-feed');
            feed.innerHTML='<article><h3>Live job</h3><p>Description</p></article>'.repeat(4);
            showTab('collection');
        }""")
        cards=page.locator('#live-feed article:visible')
        top=cards.first.bounding_box()['y']
        for card in cards.all():assert abs(card.bounding_box()['y']-top)<1
        assert page.locator('#collection-jobs').bounding_box()['y']>top
    page.evaluate("async()=>{showTab('overview');await loadSpeed();}")
    assert page.locator('#chart-speed svg > text[y="12"]').count()==0
    assert not errors
    context.close();db.engine.dispose()
