"""Browser check for following: follow from Home, reload, Feed, company page, and a setup link.

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
            check(await pg.eval_on_selector(".view-tab.active", active) == "all", "a new visitor sees Everything")
            await pg.click("#viewTabForYou")
            check(await pg.locator("#topForYou .follow-btn").count() >= 4, "For you with no follows offers companies to follow")
            first = pg.locator("#topForYou .follow-btn").first
            t1 = await first.get_attribute("data-ticker")
            await first.click()
            first = pg.locator("#topForYou .follow-btn").first
            t2 = await first.get_attribute("data-ticker")
            await first.click()
            await pg.wait_for_timeout(300)
            check(t1 != t2, "suggestions stay so several can be followed in a row")
            reasons = await pg.locator("#topForYou .follow-reason").all_inner_texts()
            check(len(reasons) > 0 and all(t1 in r or t2 in r for r in reasons), "every story says why it is there")
            check(await pg.inner_text("[data-follow-count]") == "Following 2 companies", "follow count")
            await pg.locator("#homeStoriesHeading").scroll_into_view_if_needed()
            await pg.screenshot(path=f"{out}/home-for-you.png")

            await pg.reload()
            await pg.wait_for_timeout(800)
            check(await pg.eval_on_selector(".view-tab.active", active) == "foryou", "follows and view survive a reload")
            ring = await pg.eval_on_selector_all(".orbit-slot:not([hidden])", "els => els.map(e => e.dataset.symbol)")
            check(t1 in ring and t2 in ring, "followed companies are on the ring")

            await pg.goto(base + "news.html")
            await pg.wait_for_timeout(600)
            shown = await pg.eval_on_selector_all(".news-row[data-match='1']", "els => els.map(e => e.dataset.tickers.split(','))")
            check(len(shown) > 0 and all(t1 in t or t2 in t for t in shown), "Feed For you shows only followed companies")
            await pg.click(".view-tab[data-view='all']")
            await pg.wait_for_timeout(200)
            check(await pg.locator(".news-row[data-match='1']").count() > len(shown), "Feed Everything shows all")

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
            await pg2.screenshot(path=f"{out}/phone-setup-link.png")
            await pg2.click(".setup-yes")
            await pg2.wait_for_timeout(300)
            check(sorted(await pg2.evaluate("followState().symbols")) == sorted([t1, t2]), "setup link copies the follows")
            check(await pg2.evaluate("location.hash") == "", "the link is cleared from the address bar")

            await pg2.goto(base + "index.html#follow=%3Cimg%20src=x%3E,NOTREAL")
            await pg2.wait_for_timeout(500)
            check(await pg2.evaluate("document.querySelectorAll('img[src=\"x\"]').length") == 0, "a hostile link injects nothing")
            check(sorted(await pg2.evaluate("followState().symbols")) == sorted([t1, t2]), "a hostile link changes nothing")
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
