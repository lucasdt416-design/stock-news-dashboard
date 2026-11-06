"""Browser check for following: first-visit picker, Your feed settings, Home, Feed, company page, setup link.

Usage: python scripts/check_following.py [--site .capture/site] [--out .capture/following]
Prints each step and exits 1 if any check fails or the page logs an error.
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from capture_site import serve  # noqa: E402
from playwright.async_api import async_playwright  # noqa: E402

failures = []


def check(ok, label):
    print(("ok   " if ok else "FAIL ") + label)
    if not ok:
        failures.append(label)


async def run(site, out):
    os.makedirs(out, exist_ok=True)
    httpd = serve(os.path.abspath(site))
    base = f"http://127.0.0.1:{httpd.server_address[1]}/"
    errors = []
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome")
            ctx = await browser.new_context(viewport={"width": 1280, "height": 1100})
            pg = await ctx.new_page()
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            active = "e => e.dataset.view"

            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(600)
            check(await pg.is_visible("#welcomePicker"), "a new visitor is asked what they care about")
            check(await pg.eval_on_selector(".view-tab.active", active) == "all", "a new visitor sees Everything")
            await pg.locator("#welcomePicker").scroll_into_view_if_needed()
            await pg.screenshot(path=f"{out}/home-picker.png")
            check(await pg.is_disabled("#pickerDone"), "nothing picked, nothing to confirm")
            sector = await pg.locator("#welcomePicker .chip").first.get_attribute("data-sector")
            await pg.locator("#welcomePicker .chip").first.click()
            await pg.click("#pickerDone")
            await pg.wait_for_timeout(400)
            check(not await pg.is_visible("#welcomePicker"), "the picker closes")
            check(await pg.eval_on_selector(".view-tab.active", active) == "foryou", "picking a sector opens For you")
            reasons = await pg.locator("#topForYou .follow-reason").all_inner_texts()
            check(len(reasons) > 0 and all(sector in r or "Mentions" in r for r in reasons), f"stories say they are in {sector}")
            await pg.locator("#homeStoriesHeading").scroll_into_view_if_needed()
            await pg.screenshot(path=f"{out}/home-for-you.png")

            await pg.goto(base + "settings.html")
            await pg.wait_for_timeout(600)
            check(await pg.get_attribute(f'.chip[data-sector-toggle="{sector}"]', "aria-pressed") == "true", "settings shows the picked sector")
            await pg.fill("#settingsCompanyFilter", "zzzz")
            check(await pg.is_visible("#settingsCompanyEmpty"), "company search says when nothing matches")
            await pg.fill("#settingsCompanyFilter", "")
            outside = await pg.eval_on_selector_all(
                ".settings-group li[data-follow-mark]",
                "(els, sec) => els.map(e => e.dataset.followMark).filter(s => COMPANY_SECTOR[s] !== sec)", sector)
            t1 = outside[0]
            await pg.fill("#settingsCompanyFilter", t1.lower())
            check(await pg.locator(".settings-group[open]").count() >= 1, "searching opens the matching sector")
            await pg.click(f'.settings-group .follow-btn[data-ticker="{t1}"]')
            await pg.fill("#settingsCompanyFilter", "")
            check(await pg.locator(".settings-group[open]").count() == 0, "clearing the search folds the sectors")
            await pg.click('.type-toggle[data-type-toggle="insider"]')
            await pg.wait_for_timeout(200)
            check(await pg.get_attribute('.type-toggle[data-type-toggle="insider"]', "aria-pressed") == "false", "insider trades switched off")
            check("1 company and 1 sector" in await pg.inner_text(".page-standfirst"), "settings summarises what is followed")
            check("Following the whole sector" in await pg.inner_text(f'[data-sector-group="{sector}"] [data-group-meta]'), "a followed sector says so when folded")
            await pg.screenshot(path=f"{out}/settings.png", full_page=True)

            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(800)
            check(not await pg.is_visible("#welcomePicker"), "the picker never comes back once answered")
            ring = await pg.eval_on_selector_all(".orbit-slot:not([hidden])", "els => els.map(e => e.dataset.symbol)")
            check(t1 in ring, "a followed company is on the ring")

            await pg.goto(base + "news.html")
            await pg.wait_for_timeout(600)
            rows = await pg.eval_on_selector_all(
                ".news-row[data-match='1']",
                "els => els.map(e => ({tickers: e.dataset.tickers.split(','), cat: e.dataset.category, why: e.querySelector('.follow-reason').textContent}))")
            follows = await pg.evaluate("[...followedSet()]")
            check(len(rows) > 0 and all(any(t in follows for t in r["tickers"]) for r in rows), "Feed For you shows only what is followed")
            check(all(r["cat"] != "Insider Transactions" for r in rows), "hidden story types stay out of For you")
            check(all(r["why"] for r in rows), "every Feed story says why it is there")
            await pg.screenshot(path=f"{out}/feed-for-you.png")
            await pg.click(".view-tab[data-view='all']")
            await pg.wait_for_timeout(200)
            check(await pg.locator(".news-row[data-match='1'][data-category='Insider Transactions']").count() > 0, "Everything still shows insider trades")
            check(await pg.locator(".news-row[data-match='1'] .follow-reason:not([hidden])").count() == 0, "no why lines in Everything")

            await pg.goto(base + f"company.html?ticker={t1}")
            await pg.wait_for_timeout(800)
            btn = pg.locator(f"#profile-{t1} .follow-btn")
            check(await btn.get_attribute("aria-pressed") == "true", "company page shows Following")
            await btn.click()
            check(await btn.inner_text() == "Follow", "unfollow from the company page")
            await btn.click()
            link = await pg.evaluate("setupLinkUrl()")

            phone = await browser.new_context(viewport={"width": 390, "height": 844})
            pg2 = await phone.new_page()
            pg2.on("pageerror", lambda e: errors.append(str(e)))
            await pg2.goto(link)
            await pg2.wait_for_timeout(700)
            check(await pg2.locator("#setupLinkBanner").count() == 1, "a setup link asks first on another device")
            check(not await pg2.is_visible("#welcomePicker"), "a setup link skips the first-visit question")
            await pg2.screenshot(path=f"{out}/phone-setup-link.png")
            await pg2.click(".setup-yes")
            await pg2.wait_for_timeout(300)
            state = await pg2.evaluate("followState()")
            check(state["symbols"] == [t1] and state["sectors"] == [sector] and state["hide"] == ["insider"], "setup link copies companies, sectors and hidden types")
            check(await pg2.evaluate("location.hash") == "", "the link is cleared from the address bar")
            await pg2.goto(base + "index.html#follow=%3Cimg%20src=x%3E,NOTREAL&sectors=Nope")
            await pg2.wait_for_timeout(500)
            check(await pg2.evaluate("document.querySelectorAll('img[src=\"x\"]').length") == 0, "a hostile link injects nothing")
            await pg2.goto(base + "settings.html")
            await pg2.wait_for_timeout(500)
            await pg2.screenshot(path=f"{out}/phone-settings.png")

            # Someone who just wants everything.
            fresh = await browser.new_context(viewport={"width": 1280, "height": 1100})
            pg3 = await fresh.new_page()
            pg3.on("pageerror", lambda e: errors.append(str(e)))
            await pg3.goto(base + "index.html")
            await pg3.wait_for_timeout(600)
            await pg3.click('[data-click="skipPicker"]')
            await pg3.reload()
            await pg3.wait_for_timeout(600)
            check(not await pg3.is_visible("#welcomePicker") and await pg3.eval_on_selector(".view-tab.active", active) == "all", "Show me everything sticks")

            # Start over brings back the first visit.
            pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await pg.goto(base + "settings.html")
            await pg.wait_for_timeout(400)
            await pg.click('[data-click="resetFeed"]')
            await pg.wait_for_timeout(300)
            check(await pg.evaluate("followState().symbols.length + followState().sectors.length") == 0, "Start over clears everything")
            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(600)
            check(await pg.is_visible("#welcomePicker"), "after Start over, Home asks again")
            await browser.close()
    finally:
        httpd.shutdown()
    check(not errors, f"no page errors {errors if errors else ''}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--site", default=".capture/site")
    parser.add_argument("--out", default=".capture/following")
    args = parser.parse_args()
    asyncio.run(run(args.site, args.out))
    print(f"problems: {len(failures)}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
