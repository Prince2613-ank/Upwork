from playwright.sync_api import sync_playwright
import sys
import json

sys.stdout.reconfigure(encoding='utf-8')

# Connect to Edge on 9223 or Chrome on 9222
# Let's inspect using playwright
with sync_playwright() as p:
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    page = ctx.new_page()

    api_calls = []
    page.on("request", lambda req: api_calls.append({"url": req.url, "method": req.method}) if "graphql" in req.url or "api" in req.url else None)

    page.goto("https://www.upwork.com/jobs/~022112660193329382861/", wait_until="domcontentloaded")
    page.wait_for_timeout(3000)

    # Scroll down to client history
    page.evaluate("window.scrollTo(0, 1800)")
    page.wait_for_timeout(2000)

    # Inspect all elements inside client history
    client_hist_info = page.evaluate("""() => {
        let h = Array.from(document.querySelectorAll('*')).find(el => el.innerText && el.innerText.includes("Client's recent history"));
        let card = h ? h.closest('.air3-card') : null;
        if (!card) return { found: false };

        return {
            found: true,
            cardClasses: card.className,
            innerHTML_sample: card.innerHTML.slice(0, 1000),
            cardText: card.innerText,
            allButtons: Array.from(card.querySelectorAll('button, a')).map(b => ({
                tag: b.tagName,
                text: b.innerText,
                classes: b.className,
                dataTest: b.getAttribute('data-test'),
                role: b.getAttribute('role')
            }))
        };
    }""")

    print("Client History Card Info:")
    print(json.dumps(client_hist_info, indent=2))

    print(f"\nGraphQL / API calls caught ({len(api_calls)}):")
    for req in api_calls[:15]:
        print(" ", req["method"], req["url"][:120])

    page.close()
