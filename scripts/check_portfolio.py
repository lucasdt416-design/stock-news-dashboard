"""Browser check for Your portfolio: adding, pasting, importing, editing, removing, and what gets sent.

Usage: python scripts/check_portfolio.py [--site .capture/site] [--out .capture/portfolio]
Prints each step and exits 1 if any check fails or the page logs an error.

The site's two functions only run on Cloudflare, so they are answered here with made-up replies
in the shape the real ones give. Every request the page makes is recorded, to check that nothing
but a ticker ever leaves it.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.dirname(__file__))
from capture_site import serve  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

failures = []

# Made-up answers from /api/history for tickers outside the watchlist.
MONTHS = [["2019-01", 20.0], ["2020-01", 25.0], ["2021-10", 40.0], ["2024-01", 80.0], ["2026-10", 100.0]]
HISTORY = {
    "VOO": {"name": "Demo 500 Fund", "kind": "fund", "price": 500.0, "sector": None, "industry": None},
    "RDDT": {"name": "Demo Software Co", "kind": "stock", "price": 50.0, "sector": None, "industry": "Something New"},
    "SPOT": {"name": "Demo Streaming Co", "kind": "stock", "price": 100.0, "sector": "Consumer Staples", "industry": "Consumer products"},
    "GOOG": {"name": "Demo Search Co Class C", "kind": "stock", "price": 200.0, "sector": "Technology", "industry": "Technology"},
}


def history_reply(ticker, day):
    known = HISTORY.get(ticker)
    if not known:
        return 404, {"found": False, "symbol": ticker, "error": f"No price history found for {ticker}."}
    return 200, {"found": True, "symbol": ticker, "name": known["name"], "kind": known["kind"], "currency": "USD",
                 "first_month": MONTHS[0][0], "months": MONTHS, "price": {"value": known["price"], "date": day},
                 "fetched": day, "sector": known["sector"], "industry": known["industry"]}


def check(ok, label):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


async def run(site, out):
    os.makedirs(out, exist_ok=True)
    httpd = serve(os.path.abspath(site))
    base = f"http://127.0.0.1:{httpd.server_address[1]}/"
    errors, requests = [], []
    with open(os.path.join(site, "data", "prices", "index.json"), encoding="utf-8") as f:
        index = json.load(f)["symbols"]
    day = index["NVDA"]["price"]["date"]
    nvda, aapl = index["NVDA"]["price"]["value"], index["AAPL"]["price"]["value"]

    async def api_history(route):
        ticker = parse_qs(urlparse(route.request.url).query).get("ticker", [""])[0]
        status, body = history_reply(ticker, day)
        await route.fulfill(status=status, content_type="application/json", body=json.dumps(body))

    async def api_lookup(route):
        q = parse_qs(urlparse(route.request.url).query).get("q", [""])[0]
        body = {"found": True, "symbol": "SPOT"} if q.lower() == "spotify" else {"found": False}
        await route.fulfill(status=200 if body["found"] else 404, content_type="application/json", body=json.dumps(body))

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome")
            ctx = await browser.new_context(viewport={"width": 1280, "height": 1100})
            await ctx.route("**/api/history*", api_history)
            await ctx.route("**/api/lookup*", api_lookup)
            pg = await ctx.new_page()
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" and "404" not in m.text else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.on("request", lambda r: requests.append((r.method, r.url.replace(base, "/"), r.post_data)))
            await pg.add_init_script("""document.addEventListener('securitypolicyviolation', e => {
                console.error('CSP violation: ' + e.violatedDirective + ' ' + e.blockedURI); });""")
            pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))

            async def status():
                return await pg.inner_text("#pfStatus")

            async def stored():
                return await pg.evaluate("JSON.parse(localStorage.getItem('stockpulse_portfolio') || 'null')")

            async def add(ticker, amount, mode="shares"):
                await pg.click(f'[data-pf-mode="{mode}"]')
                await pg.fill("#pfTicker", ticker)
                await pg.fill("#pfAmount", amount)
                await pg.click('[data-click="pfAddOne"]')
                await pg.wait_for_timeout(350)

            async def row_text(ticker):
                return await pg.inner_text(f'.pf-row[data-ticker="{ticker}"]')

            await pg.goto(base + "portfolio.html")
            await pg.wait_for_timeout(500)
            check(await pg.is_visible("#pfEmpty") and not await pg.is_visible("#pfHoldings"), "a new visitor sees the empty state")
            check(await pg.is_visible("#pfDemo"), "the demo site says its prices aren't real")
            check("not advice" in await pg.inner_text(".pf-foot"), "the page says it isn't advice")
            await pg.screenshot(path=f"{out}/empty.png")

            # One at a time
            await add("nvda", "10")
            check("Added NVDA" in await status(), "a watchlist ticker is added in any case")
            text = await row_text("NVDA")
            check("10 shares" in text and f"{nvda * 10:,.2f}" in text, "its value is shares times the price in the price file")
            check(await pg.get_attribute('.pf-row[data-ticker="NVDA"] a.pf-ticker', "href") == "company-nvda.html", "it links to the company page")
            await add("NVDA", "5")
            check("You now have 15 shares" in await status() and await pg.locator(".pf-row").count() == 1, "adding it again makes one holding of 15")
            await add("Apple", "2,000", mode="dollars")
            shares = (await stored())["holdings"][1]["sh"]
            check(abs(shares - 2000 / aapl) < 1e-5, "dollars become shares at the latest price (a company name works too)")
            await add("VOO", "4")
            check("Fund" in await row_text("VOO") and "2,000.00" in await row_text("VOO"), "a fund outside the watchlist is priced by the server and marked Fund")
            await add("Spotify", "3")
            check("SPOT" in await pg.inner_text("#pfList") and "Consumer Staples" in await row_text("SPOT"), "a company name outside the watchlist is found through lookup, with its sector")
            await add("ZZZZQ", "1")
            check("couldn’t find" in await status() and "ZZZZQ" not in await pg.inner_text("#pfList"), "a ticker that doesn't exist is refused in plain words")
            await add("NVDA", "-3")
            check("how many shares" in await status(), "a negative amount is refused")
            await add("<img src=x onerror=window.__xss=1>", "1")
            check("couldn’t find" in await status(), "markup typed as a ticker is refused")

            # Paste
            await pg.click('[data-click="pfTogglePaste"]')
            await pg.fill("#pfPasteText", 'MSFT 2, RDDT $1,000\nGOOG 1 @ 150\nZZZZQ 9\nNVDA\n<img src=x onerror=window.__xss=1> 4')
            await pg.click('[data-click="pfReadPaste"]')
            await pg.wait_for_timeout(600)
            preview = await pg.inner_text("#pfPreview")
            check("MSFT" in preview and "2 shares" in preview, "the preview lists what was read")
            check("about 20 shares" in preview, "a pasted dollar amount shows the shares it becomes")
            check("paid $150.00" in preview, "“@ 150” is read as what was paid")
            check("couldn’t find this ticker" in preview, "a ticker that doesn't exist is flagged, not dropped")
            check("2 lines couldn’t be read" in preview and "no amount" in preview, "lines that couldn't be read are shown with the reason")
            check(await pg.locator("#pfPreview img").count() == 0, "pasted markup stays text")
            check((await stored())["holdings"][-1]["t"] == "SPOT", "nothing is saved before Add")
            await pg.screenshot(path=f"{out}/preview.png", full_page=True)
            check(await pg.inner_text('[data-click="pfAcceptPreview"]') == "Add these 3", "the button says how many will be added")
            await pg.click('[data-click="pfAcceptPreview"]')
            await pg.wait_for_timeout(300)
            tickers = [h["t"] for h in (await stored())["holdings"]]
            check(tickers == ["NVDA", "AAPL", "VOO", "SPOT", "MSFT", "RDDT", "GOOG"], f"the readable rows are saved {tickers}")
            await pg.click("#pfShowAll")
            check("Sector unknown" in await row_text("RDDT"), "an industry that isn't in the table shows as Sector unknown")
            check("Technology" in await row_text("GOOG") and await pg.get_attribute('.pf-row[data-ticker="GOOG"] a.pf-ticker', "href") == "company-googl.html",
                  "GOOG is treated as the same company as GOOGL")

            # Import a file
            with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
                f.write('"Positions as of today"\r\n\r\n"Symbol","Description","Quantity","Cost Basis"\r\n'
                        '"JPM","A BANK","7","$1,400.00"\r\n"Cash & Cash Investments","--","--","--"\r\n'
                        '"=HYPERLINK(""http://x"")","x","1","1"\r\n"Account Total","--","--","$1,400.00"\r\n')
                csv_path = f.name
            await pg.set_input_files("#pfFile", csv_path)
            await pg.wait_for_timeout(500)
            preview = await pg.inner_text("#pfPreview")
            check("From your file" in preview and "7 shares, paid $1,400.00" in preview, "a broker file is read, with its cost basis")
            check("3 lines couldn’t be read" in preview, "cash, totals and odd rows are flagged")
            await pg.click('[data-click="pfAcceptPreview"]')
            await pg.wait_for_timeout(300)
            check("+" in await row_text("JPM") or "−" in await row_text("JPM"), "a holding with a cost shows its gain or loss")
            os.unlink(csv_path)

            # Edit, sector by hand, remove
            await pg.click('.pf-row[data-ticker="RDDT"] [data-click="pfEditOne"]')
            await pg.select_option("#pfEditSector", "Technology")
            await pg.fill("#pfEditShares", "30")
            await pg.click('[data-click="pfSaveEdit"]')
            await pg.wait_for_timeout(200)
            check("30 shares" in await row_text("RDDT") and "Technology (set by you)" in await row_text("RDDT"), "shares and a hand-set sector are saved and marked")
            await pg.click('.pf-row[data-ticker="MSFT"] [data-click="pfEditOne"]')
            check(await pg.locator("#pfEditSector").count() == 0, "a watchlist company's sector can't be overridden")
            await pg.click('[data-click="pfRemoveOne"]')
            await pg.wait_for_timeout(200)
            check("MSFT" not in [h["t"] for h in (await stored())["holdings"]], "one holding can be removed")
            weights = await pg.eval_on_selector_all(".pf-row-weight", "els => els.map(e => parseFloat(e.textContent) || 0)")
            check(abs(sum(weights) - 100) < 1.5, f"the shares of the total add up to 100% ({sum(weights):.1f})")
            await pg.screenshot(path=f"{out}/holdings.png", full_page=True)

            # The X-ray, on a portfolio whose answers can be worked out by hand
            price = lambda t: HISTORY[t]["price"] if t in HISTORY else index[t]["price"]["value"]  # noqa: E731
            want = {"NVDA": 4000, "AMD": 2000, "MSFT": 2000, "VOO": 1500, "RDDT": 500}  # dollars of each, 10,000 in all
            await pg.evaluate("h => localStorage.setItem('stockpulse_portfolio', JSON.stringify({v: 1, holdings: h}))",
                              [{"t": t, "sh": v / price(t)} for t, v in want.items()])
            await pg.reload()
            await pg.wait_for_timeout(700)
            # The summary: the big number, the line, and each holding's dollars over the same range
            money = lambda text: float(text.replace("−", "-").replace("$", "").replace(",", "").replace("+", "").split()[0])  # noqa: E731
            check(await pg.inner_text("#pfHeroValue") == "$10,000.00", "the big number is the total")
            check(await pg.locator("#pfValueChart .pf-line").count() == 1, "the value over time is drawn as one line")
            check(await pg.locator(".pf-row .pf-spark").count() >= 3, "holdings with a year of prices get a small line")
            moved = [money(t) for t in await pg.locator(".pf-move-amount").all_inner_texts()]
            headline = money(await pg.inner_text("#pfHeroChange"))
            check(len(moved) >= 2 and abs(sum(moved) - headline) < 0.05, f"the holdings' dollar changes add up to the headline change ({sum(moved):.2f} vs {headline:.2f})")
            box = await pg.locator("#pfValueChart svg").bounding_box()
            await pg.mouse.move(box["x"] + box["width"] * 0.3, box["y"] + box["height"] / 2)
            check("were worth at the end of" in await pg.inner_text("#pfHeroLabel") and await pg.inner_text("#pfHeroValue") != "$10,000.00",
                  "pointing at the line shows that month's value")
            await pg.mouse.move(2, 2)
            check(await pg.inner_text("#pfHeroValue") == "$10,000.00", "and moving away shows today's again")
            sectors = await pg.inner_text("#pfSectors")
            check("$8,000.00 of your $10,000.00 is in Technology (80%)" in await pg.inner_text("#pfSectorLead"), "the largest sector is stated as a fact, in dollars")
            check("Funds (contents not broken out)" in sectors and "15%" in sectors and "Sector unknown" in sectors and "5.0%" in sectors,
                  "funds and unknown sectors are their own groups")
            conc = await pg.inner_text("#pfConcentration")
            # Stocks: 4000, 2000, 2000, 500 of 8500 -> largest 47%; 1 / (0.4706^2 + 2 * 0.2353^2 + 0.0588^2) = 2.98
            check("47%" in conc and "NVDA" in conc, "largest holding is its share of the stocks, funds left out")
            check("behave like about 3 equal-sized ones" in await pg.inner_text("#pfConcentrationLead"), "the effective number matches the hand calculation (2.98)")
            check("Funds are 15% of your portfolio and aren’t counted here" in await pg.inner_text("#pfConcentrationNote"), "the funds' share is said beside it")
            overlap = await pg.inner_text("#pfOverlap")
            # NVDA 4000 + AMD 2000 + MSFT 2000 of 10,000 share the data center theme; only the first two share the China one.
            check("80% of your portfolio is sensitive to spending on AI and data centers: NVDA, AMD and MSFT." in overlap
                  and "60% of your portfolio is sensitive to US export controls on China: NVDA and AMD." in overlap,
                  "a shared theme names its holdings and sums their shares")
            check("RDDT" in await pg.inner_text("#pfOverlapNote") and "Funds aren’t looked into" in await pg.inner_text("#pfOverlapNote"),
                  "it says which holdings it couldn't see")
            check("15% of your portfolio is in a fund: VOO" in await pg.inner_text("#pfFunds"), "funds are shown as not broken out")
            check(not await pg.is_visible("#pfGainSection"), "no gain section without a cost")
            await pg.screenshot(path=f"{out}/xray.png", full_page=True)

            # Cost without a date: gain, but no S&P 500 comparison. With a date: the comparison.
            await pg.click('.pf-row[data-ticker="NVDA"] [data-click="pfEditOne"]')
            await pg.fill("#pfEditPaid", "1000")
            await pg.click('[data-click="pfSaveEdit"]')
            await pg.wait_for_timeout(300)
            check("+$3,000.00 (+300%)" in await pg.inner_text("#pfGainLead"), "gain is value against cost")
            check("Add the month you bought" in await pg.inner_text("#pfGainSpy"), "a cost with no date gets no S&P 500 comparison")
            with open(os.path.join(site, "data", "prices", "SPY.json"), encoding="utf-8") as f:
                spy = json.load(f)
            month, start = spy["months"][-37]
            await pg.click('.pf-row[data-ticker="NVDA"] [data-click="pfEditOne"]')
            await pg.fill("#pfEditBought", month)
            await pg.click('[data-click="pfSaveEdit"]')
            await pg.wait_for_timeout(600)
            same = 1000 * spy["price"]["value"] / start
            check(f"${same:,.2f}" in await pg.inner_text("#pfGainSpy"), f"the same money in the S&P 500 is cost times its rise since that month (${same:,.2f})")
            check("dividends" in await pg.inner_text("#pfGainNote"), "the comparison says what it includes")

            # What if: the page's answers against the same sums done here from the price files
            def load(t):
                with open(os.path.join(site, "data", "prices", f"{t}.json"), encoding="utf-8") as f:
                    return json.load(f)

            nv, sp = load("NVDA"), load("SPY")
            start_month, start_price = nv["months"][-37]
            spy_start = dict(sp["months"])[start_month]

            async def what_if(ticker, amount, month, monthly=""):
                await pg.fill("#wiTicker", ticker)
                await pg.fill("#wiAmount", amount)
                await pg.fill("#wiFrom", month)
                await pg.fill("#wiMonthly", monthly)
                await pg.click('[data-click="wiRun"]')
                await pg.wait_for_timeout(500)
                return await pg.inner_text("#wiResult") if await pg.is_visible("#wiResult") else ""

            check(await pg.input_value("#wiFrom") != "" and await pg.get_attribute('[data-wi-years="5"]', "aria-pressed") == "true", "the form starts on 5 years ago")
            result = await what_if("NVDA", "1000", start_month)
            value = 1000 * nv["price"]["value"] / start_price
            check(f"${value:,.2f}" in result, f"a lump sum is the amount times price now over price then (${value:,.2f})")
            same = 1000 * sp["price"]["value"] / spy_start
            check(f"${same:,.2f}" in result and "S&P 500" in result, f"the same money in the S&P 500 is worked the same way (${same:,.2f})")
            check("a year" in result and "dividends were reinvested" in result and "Ignores taxes and fees" in result, "it gives a yearly rate and says what it assumes")
            check("demo prices" in result, "on the demo site the result says the prices aren't real")
            check(await pg.locator("#wiResult svg.wi-chart path.wi-line").count() == 2, "the chart draws the stock and the S&P 500")
            query = urlparse(pg.url).query
            check(parse_qs(query) == {"t": ["NVDA"], "a": ["1000"], "from": [start_month]}, f"the address holds the ticker, amount and month and nothing else ({query})")
            await pg.click('[data-click="wiToggleNumbers"]')
            check(await pg.locator(".wi-table tbody tr").count() == 38, "the numbers behind the chart can be shown: 37 months and now")
            await pg.screenshot(path=f"{out}/what-if.png", full_page=True)

            shares = 1000 / start_price + sum(100 / price for month, price in nv["months"][-36:])
            result = await what_if("NVDA", "1000", start_month, "100")
            check(f"${shares * nv['price']['value']:,.2f}" in result and "$4,600.00" in result, "monthly amounts are bought at each month's real price (36 of them: $4,600 put in)")
            check("m=100" in pg.url, "the monthly amount is in the link")

            first_month = nv["months"][0][0]
            await pg.fill("#wiMonthly", "")
            result = await what_if("NVDA", "1000", "1980-01")
            check(result == "" or "started trading" in await pg.inner_text("#wiStatus"), "a start before the first month isn't guessed")
            check("started trading" in await pg.inner_text("#wiStatus"), "it says when the stock started trading")
            await pg.click('[data-click="wiUseFirst"]')
            await pg.wait_for_timeout(500)
            check(f"from={first_month}" in pg.url, "and offers the first month, which then runs")
            await pg.click('[data-wi-years="first"]')
            await pg.fill("#wiTicker", "RDDT")
            await pg.click('[data-click="wiRun"]')
            await pg.wait_for_timeout(500)
            # RDDT is answered by the made-up server reply: 20.0 in 2019-01, 50.0 now -> $1,000 becomes $2,500
            check("$2,500.00" in await pg.inner_text("#wiResult") and "January 2019" in await pg.inner_text("#wiResult"), "a ticker outside the watchlist works, from its first month")
            await what_if("ZZZZQ", "1000", start_month)
            check("couldn’t find" in await pg.inner_text("#wiStatus"), "a ticker that doesn't exist is refused in plain words")
            await what_if("NVDA", "abc", start_month)
            check("Type an amount" in await pg.inner_text("#wiStatus"), "a bad amount is refused")

            # A shared link, including a hostile one
            await pg.goto(base + f"portfolio.html?t=AAPL&a=250&from={start_month}")
            await pg.wait_for_timeout(700)
            ap = load("AAPL")
            check(f"${250 * ap['price']['value'] / dict(ap['months'])[start_month]:,.2f}" in await pg.inner_text("#wiResult"), "a shared link fills the form and shows the result")
            await pg.goto(base + "portfolio.html?t=%3Cimg%20src%3Dx%20onerror%3Dwindow.__xss%3D1%3E&a=1e99&from=x")
            await pg.wait_for_timeout(500)
            check(not await pg.is_visible("#wiResult") and await pg.input_value("#wiTicker") == "", "a link with bad values is ignored")

            # The whole portfolio: NVDA 4000, AMD 2000, MSFT 2000, VOO 1500, RDDT 500 of 10,000
            await pg.goto(base + "portfolio.html")
            await pg.wait_for_timeout(600)
            await pg.fill("#wiAmount", "10000")
            await pg.fill("#wiFrom", start_month)
            await pg.click('[data-click="wiRunPortfolio"]')
            await pg.wait_for_timeout(700)

            def grown(t, dollars):
                if t in HISTORY:
                    then = [v for m, v in MONTHS if m <= start_month][-1]
                    return dollars * HISTORY[t]["price"] / then
                data = load(t)
                return dollars * data["price"]["value"] / dict(data["months"])[start_month]

            young = [t for t in want if t not in HISTORY and load(t)["months"][0][0] > start_month]
            kept = {t: v for t, v in want.items() if t not in young}
            expected = sum(grown(t, 10000 * v / sum(kept.values())) for t, v in kept.items())
            result = await pg.inner_text("#wiResult")
            check(f"${expected:,.2f}" in result or f"${expected:,.0f}" in result, f"the portfolio run splits the amount by today's weights (${expected:,.2f})")
            check("Uses today’s mix" in result, "it says it uses today's mix")
            check(urlparse(pg.url).query == "", "a portfolio run puts nothing in the address")
            check(await pg.locator('[data-click="wiCopyLink"]').count() == 0, "and offers no link to share")
            await pg.screenshot(path=f"{out}/what-if-portfolio.png", full_page=True)

            # Only funds
            await pg.evaluate("localStorage.setItem('stockpulse_portfolio', JSON.stringify({v: 1, holdings: [{t: 'VOO', sh: 2}, {t: 'SPY', sh: 1}]}))")
            await pg.reload()
            await pg.wait_for_timeout(600)
            check("Everything here is a fund" in await pg.inner_text("#pfConcentrationLead") and await pg.locator("#pfConcentration .pf-stat").count() == 0,
                  "a portfolio of only funds gets one sentence, not numbers")
            await pg.evaluate("h => localStorage.setItem('stockpulse_portfolio', JSON.stringify({v: 1, holdings: h}))",
                              [{"t": t, "sh": 3} for t in ["NVDA", "AAPL", "VOO", "SPOT", "RDDT", "GOOG", "JPM"]])

            # Follow these companies, and what a setup link then carries
            await pg.reload()
            await pg.wait_for_timeout(600)
            note = await pg.inner_text("#pfFollowNote")
            check("to For you" in note and "doesn’t share what you hold" in note, "following is offered, and says it doesn't share holdings")
            await pg.click("#pfFollow")
            await pg.wait_for_timeout(300)
            followed = await pg.evaluate("JSON.parse(localStorage.getItem('stockpulse_follow')).symbols.sort()")
            check(followed == ["AAPL", "GOOGL", "JPM", "NVDA"], f"only companies StockPulse follows are followed, GOOG as GOOGL ({followed})")
            check(not await pg.is_visible("#pfFollow") and "You follow all 4" in await pg.inner_text("#pfFollowNote"), "the button goes once they're followed")
            link = await pg.evaluate("setupLinkUrl()")
            check("follow=" in link and not any(t in link for t in ("VOO", "SPOT", "RDDT")) and not any(c.isdigit() for c in link.split("#")[1]),
                  "a setup link carries the followed companies only: no other holding, no amounts")
            reading = await pg.evaluate("localStorage.getItem('stockpulse_reading') || ''")
            check(not any(t in reading for t in ("VOO", "SPOT", "RDDT")), "holdings don't go into the reading history")
            check(await pg.get_attribute('.sidebar-nav a[href="portfolio.html"]', "class") is not None
                  and "active" in await pg.get_attribute('.sidebar-nav a[href="portfolio.html"]', "class"), "the menu shows Portfolio as the open page")
            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(500)
            check(await pg.is_visible('.hero-copy a[href="portfolio.html"]'), "Home links to the page")
            await pg.goto(base + "portfolio.html")
            await pg.wait_for_timeout(500)

            # Survives a reload; bad stored data is dropped and said
            await pg.reload()
            await pg.wait_for_timeout(600)
            check(await pg.locator(".pf-row").count() >= 5 and "$" in await pg.inner_text("#pfTotal"), "holdings are still there after a reload")
            await pg.evaluate("""() => { const s = JSON.parse(localStorage.getItem('stockpulse_portfolio'));
                s.holdings.push({t: '<b>x</b>', sh: 1}, {t: 'KO', sh: -4}); localStorage.setItem('stockpulse_portfolio', JSON.stringify(s)); }""")
            await pg.reload()
            await pg.wait_for_timeout(500)
            check("2 saved holdings couldn’t be read" in await pg.inner_text("#pfDropped"), "bad stored rows are left out and counted")
            check(await pg.evaluate("window.__xss === undefined"), "nothing typed, pasted, imported or stored ran as script")

            # What left the browser
            sent = [u for m, u, body in requests if "/api/" in u]
            check(all(m == "GET" and body is None for m, u, body in requests), "every request is a plain GET with no body")
            asked = sorted({parse_qs(urlparse(u).query).get("ticker", parse_qs(urlparse(u).query).get("q", [""]))[0] for u in sent})
            check(not ({"NVDA", "AAPL", "MSFT", "JPM", "Apple"} & set(asked)), f"watchlist companies are never sent to the server {asked}")
            check(all(set(parse_qs(urlparse(u).query)) <= {"ticker", "q"} for u in sent), "only a ticker or a name is ever in a request")
            numbers = ("=10", "=15", "2000", "1400", "=30", "150")
            check(not any(n in u for u in sent for n in numbers), "no share count, amount or cost appears in any request")
            first = len([u for u in sent if "ticker=VOO" in u])
            check(first == 1, f"a ticker outside the watchlist is asked for once, then kept in the browser ({first})")
            check(not any("ticker=SPY" in u for u in sent), "the S&P 500 comparison reads a static file, not the server")

            # Remove everything
            await pg.click('[data-click="pfRemoveAll"]')
            await pg.wait_for_timeout(300)
            check(await stored() is None and await pg.evaluate("localStorage.getItem('stockpulse_prices')") is None, "Remove everything clears the holdings and the kept prices")
            check(await pg.is_visible("#pfEmpty"), "and the page is empty again")

            # Phone width
            phone = await browser.new_context(viewport={"width": 390, "height": 844})
            await phone.route("**/api/history*", api_history)
            await phone.add_init_script("""try { if (!localStorage.getItem('stockpulse_portfolio')) localStorage.setItem('stockpulse_portfolio', JSON.stringify({v: 1, holdings: [
                {t: 'NVDA', sh: 12.5, paid: 900, bought: '2021-06'}, {t: 'BRK-B', sh: 3}, {t: 'VOO', sh: 4}, {t: 'JPM', sh: 20, paid: 5000}]})); } catch (e) {}""")
            small = await phone.new_page()
            small.on("pageerror", lambda e: errors.append(str(e)))
            await small.goto(base + "portfolio.html")
            await small.wait_for_timeout(700)
            overflow = await small.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
            check(overflow <= 0, f"no sideways scrolling at 390 px ({overflow}px)")
            tabs = await small.eval_on_selector_all(".mobile-bottom-nav a", "els => els.map(e => e.textContent.trim())")
            check(tabs == ["Home", "Portfolio", "Moves", "Companies", "Feed"], f"the phone tab bar has Portfolio and still five tabs ({tabs})")
            fits = await small.evaluate("(() => { const n = document.querySelector('.mobile-bottom-nav'); return n.scrollWidth <= n.clientWidth + 1; })()")
            check(fits, "and they fit")
            await small.screenshot(path=f"{out}/phone.png", full_page=True)
            await browser.close()
    finally:
        httpd.shutdown()
    check(not errors, f"no page errors {errors if errors else ''}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default=".capture/site")
    parser.add_argument("--out", default=".capture/portfolio")
    args = parser.parse_args()
    asyncio.run(run(args.site, args.out))
    print(f"problems: {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
