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
    "NFLX": {"name": "Demo Streaming Co", "kind": "stock", "price": 100.0, "sector": "Consumer Staples", "industry": "Media"},
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
        body = {"found": True, "symbol": "NFLX"} if q.lower() == "netflix" else {"found": False}
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
            await add("Netflix", "3")
            check("NFLX" in await pg.inner_text("#pfList") and "Consumer Staples" in await row_text("NFLX"), "a company name outside the watchlist is found through lookup, with its sector")
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
            check((await stored())["holdings"][-1]["t"] == "NFLX", "nothing is saved before Add")
            await pg.screenshot(path=f"{out}/preview.png", full_page=True)
            check(await pg.inner_text('[data-click="pfAcceptPreview"]') == "Add these 3", "the button says how many will be added")
            await pg.click('[data-click="pfAcceptPreview"]')
            await pg.wait_for_timeout(300)
            tickers = [h["t"] for h in (await stored())["holdings"]]
            check(tickers == ["NVDA", "AAPL", "VOO", "NFLX", "MSFT", "RDDT", "GOOG"], f"the readable rows are saved {tickers}")
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
