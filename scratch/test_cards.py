from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    browser = pw.chromium.connect_over_cdp("http://127.0.0.1:9222")
    ctx = browser.contexts[0]
    page = ctx.pages[0]
    cards = page.evaluate("""() => {
        const arts = [...document.querySelectorAll('article,li[data-test],[data-test="job-tile"]')];
        return arts.map(a => {
            const tEl = a.querySelector('h2,h3,[data-test="job-title"]');
            const timeEl = a.querySelector('time, [data-test="posted-on"]');
            return {
                title: tEl ? tEl.innerText.trim() : '',
                time_html: timeEl ? timeEl.outerHTML : 'NO_TIME_EL',
                time_attr: timeEl ? timeEl.getAttribute('datetime') : null,
                time_text: timeEl ? timeEl.innerText.trim() : null
            };
        }).filter(c => c.title).slice(0, 5);
    }""")
    for c in cards:
        print(c)
