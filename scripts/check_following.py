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
            ctx = await browser.new_context(viewport={"width": 1280, "height": 1100}, accept_downloads=True)
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
            check(await pg.locator(".settings-group[open]:not(#settingsFollowing)").count() == 0, "clearing the search folds the sectors")
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
            check(await pg.evaluate("matchingStories().some(it => it.category === 'Insider Transactions')"), "Everything still shows insider trades")
            check(await pg.locator(".news-row[data-match='1'] .follow-reason:not([hidden])").count() == 0, "no why lines in Everything")

            # Learning from what you read: on by default, only For you, and never sent anywhere.
            await pg.goto(base + "news.html")
            await pg.wait_for_timeout(500)
            check(await pg.evaluate("readingState().on") and await pg.evaluate("readingState().events.length") == 0, "learning starts on, with nothing noted")
            await pg.click(".view-tab[data-view='foryou']")
            await pg.wait_for_timeout(200)
            await pg.evaluate("document.addEventListener('click', e => { if (e.target.closest('a[href^=\"http\"]')) e.preventDefault(); })")
            requests = []
            pg.on("request", lambda r: requests.append(r.url) if "127.0.0.1" not in r.url else None)
            first = pg.locator(".news-row .feed-headline a").first
            row = first.locator("xpath=ancestor::article[1]")
            want = [await row.get_attribute("data-ticker"), await pg.evaluate(
                "r => storyType(r.dataset.source, r.dataset.category)", await row.element_handle())]
            await first.click()
            got = await pg.evaluate("readingState().events.map(e => [e[1], e[2]])")
            check(got == [want], "opening a story notes its company and kind")
            check(not requests, "noting a read sends nothing anywhere")
            follows = await pg.evaluate("[...followedSet()]")
            ranked = await pg.evaluate("matchingStories().map(it => it.ticker)")
            # Read a company from the middle of For you a few times, and its stories should come up.
            low = ranked[len(ranked) // 2]
            await pg.evaluate(f"""(() => {{ const now = Math.floor(Date.now() / 1000);
                writeReading({{ on: true, events: [0, 1, 2, 3].map(i => [now - 7200 * (i + 1), '{low}', 'news']) }}); }})()""")
            await pg.reload()
            await pg.wait_for_timeout(500)
            reranked = await pg.evaluate("matchingStories().map(it => it.ticker)")
            spots = lambda order: sum(i for i, t in enumerate(order) if t == low)
            check(spots(reranked) < spots(ranked), f"For you moves {low} up after reading it")
            await pg.click("#sortDateBtn")
            await pg.wait_for_timeout(200)
            check(any(f"you often read {low}" in r for r in await pg.locator(".news-row .follow-reason").all_inner_texts()), "a moved story says why")
            await pg.click("#sortScoreBtn")
            await pg.click(".view-tab[data-view='all']")
            await pg.wait_for_timeout(200)
            check(all(it == 0 for it in await pg.evaluate("matchingStories().map(it => it.read.boost)")), "Everything ignores reading")
            await pg.click(".view-tab[data-view='foryou']")
            outsider = await pg.evaluate("[...KNOWN_SYMBOLS].find(s => !followedSet().has(s))")
            await pg.evaluate(f"""(() => {{ const now = Math.floor(Date.now() / 1000);
                writeReading({{ on: true, events: [...readingState().events, ...[1, 2, 3].map(i => [now - 60 * i, '{outsider}', 'results'])] }}); }})()""")
            check(outsider not in await pg.evaluate("matchingStories().map(it => it.ticker)"), "reading never adds unfollowed companies to For you")
            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(600)
            check(f"You’ve read about {outsider} 3 times" in await pg.inner_text("#topForYou"), "Home suggests a company you keep reading")
            await pg.goto(base + "settings.html")
            await pg.wait_for_timeout(500)
            check("You read most about" in await pg.inner_text("#learningDetail") and low in await pg.inner_text("#learningDetail"), "Your feed says what it learned")
            await pg.locator("#learningToggle").scroll_into_view_if_needed()
            await pg.screenshot(path=f"{out}/settings-learning.png")
            check("setup" not in await pg.evaluate("JSON.stringify(readingState())") and "reading" not in await pg.evaluate("setupLinkUrl()"), "the setup link leaves reading out")
            await pg.click("#learningToggle")
            check(await pg.get_attribute("#learningToggle", "aria-pressed") == "false" and await pg.inner_text("#learningStatus") == "Off", "learning can be switched off")
            check(await pg.evaluate("readingRanker()('" + low + "', 'news').boost") == 0, "switched off, it changes nothing")
            n = await pg.evaluate("readingState().events.length")
            await pg.evaluate(f"noteRead('{low}', 'filings')")
            check(await pg.evaluate("readingState().events.length") == n, "switched off, nothing new is noted")
            await pg.click("#learningToggle")
            pg.once("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await pg.click("#forgetReadingBtn")
            await pg.wait_for_timeout(200)
            check(await pg.evaluate("readingState().events.length") == 0 and await pg.is_disabled("#forgetReadingBtn"), "Forget what I read clears it")
            await pg.goto(base + f"company.html?ticker={t1}")
            await pg.wait_for_timeout(800)
            check(await pg.evaluate("readingState().events.map(e => e[1] + ':' + e[2])") == [f"{t1}:page"], "visiting a company page counts")

            await pg.goto(base + f"company.html?ticker={t1}")
            await pg.wait_for_timeout(800)
            check(pg.url.endswith(f"company-{t1.lower()}.html"), "an old company link opens the company's own page")
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

            # Tonight's additions, on the desktop session that follows things.
            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(600)
            tabs_box = await pg.locator(".hero-tabs").bounding_box()
            head_box = await pg.locator(".hero-headline").bounding_box()
            check(tabs_box["y"] + tabs_box["height"] <= head_box["y"], "For you / Everything sit above Welcome")
            hit = await pg.evaluate("(() => { const b = document.getElementById('viewTabAll').getBoundingClientRect(); return document.elementFromPoint(b.left + 8, b.top + 8)?.id; })()")
            check(hit == "viewTabAll", "nothing covers the tabs")
            if await pg.locator(".trend-item").count():
                trend = pg.locator(".trend-item .follow-btn[aria-pressed='false']").first
                tsym = await trend.get_attribute("data-ticker")
                await trend.click()
                await pg.wait_for_timeout(200)
                check(tsym in await pg.evaluate("followState().symbols"), "Follow from Trending works")
                await pg.evaluate(f"toggleFollow('{tsym}')")
            await pg.evaluate("localStorage.setItem('stockpulse_last_visit', '2000-01-01 00:00:00'); sessionStorage.clear()")
            await pg.reload()
            await pg.wait_for_timeout(700)
            check(await pg.is_visible("#heroSince") and "since your last visit" in await pg.inner_text("#heroSince"), "Home says what is new since the last visit")
            check(await pg.locator(".new-badge:not([hidden])").count() > 0, "new stories are marked New")
            await pg.reload()
            await pg.wait_for_timeout(500)
            check(await pg.is_visible("#heroSince"), "the since-last-visit line survives a reload")

            await pg.goto(base + "company.html")
            await pg.wait_for_timeout(700)
            chips = await pg.locator(".following-chip").all_inner_texts()
            check(t1 in chips, "Companies shows a Following strip at the top")
            check(await pg.locator("#followingSection .company-strip-pill").count() == len(chips), "the directory starts with a Following group")
            await pg.click(f'.following-chip >> text="{t1}"')
            await pg.wait_for_url(f"**/company-{t1.lower()}.html")
            await pg.wait_for_timeout(400)
            check(await pg.is_visible(f"#profile-{t1}"), "a Following chip opens that company")
            check(await pg.locator(f'.following-chip[aria-current="page"]').inner_text() == t1, "its chip is marked as the page you're on")
            check(await pg.locator(".company-profile-container").count() == 1, "a company page holds just that company")
            await pg.goto(base + "company.html?ticker=ZZZQ")
            await pg.wait_for_timeout(400)
            check(await pg.is_visible("#companyMissing") and "ZZZQ" in await pg.inner_text("#companyMissing"), "an unknown ticker says it isn't covered")
            await pg.goto(base + "company.html?ticker=%3Cimg%20src%3Dx%3E")
            await pg.wait_for_timeout(300)
            check(await pg.evaluate("document.querySelectorAll('img[src=\"x\"]').length") == 0, "a hostile ticker injects nothing")

            # The feed builds rows from data: it can reach stories beyond the rows the server wrote.
            await pg.goto(base + "news.html")
            await pg.wait_for_timeout(500)
            await pg.click(".view-tab[data-view='all']")
            total = await pg.evaluate("FEED.length")
            await pg.click("#sortDateBtn")
            await pg.wait_for_timeout(200)
            shown = await pg.locator(".news-row").count()
            check(shown == min(total, 60), f"by date shows the first 60 of {total}")
            if total > 60:
                await pg.click(".feed-more[data-key='all']")
                await pg.wait_for_timeout(200)
                check(await pg.locator(".news-row").count() == min(total, 110), "Show more adds the next 50")
            last = await pg.evaluate("[...FEED].sort((a, b) => a.score - b.score)[0]")
            await pg.fill("#searchInput", last["headline"][:40])
            await pg.wait_for_timeout(200)
            heads = await pg.locator(".news-row .feed-headline").all_inner_texts()
            check(any(last["headline"][:40] in h for h in heads), "search finds the least important story too")
            await pg.click("#sortScoreBtn")
            await pg.click("#feedClearFilters")

            await pg.goto(base + "settings.html")
            await pg.wait_for_timeout(500)
            check(await pg.locator("#settingsFollowingList li").count() == 1, "Your feed lists followed companies first")

            await pg.goto(base + "calendar.html")
            await pg.wait_for_timeout(500)
            if await pg.locator(".agenda-event").count():
                await pg.click(".view-tab[data-view='all']")
                await pg.wait_for_timeout(150)
                total = await pg.locator(".agenda-event:not([hidden])").count()
                await pg.click(".view-tab[data-view='foryou']")
                await pg.wait_for_timeout(150)
                mine = await pg.eval_on_selector_all(".agenda-event:not([hidden])", "els => els.map(e => e.dataset.ticker)")
                follows = await pg.evaluate("[...followedSet()]")
                check(all(t in follows for t in mine) and len(mine) <= total, "Calendar For you shows only followed companies")
                await pg.click(".view-tab[data-view='all']")
                async with pg.expect_download() as dl:
                    await pg.locator(".agenda-add").first.click()
                ics = open(await (await dl.value).path()).read()
                check(ics.startswith("BEGIN:VCALENDAR") and "DTSTART;VALUE=DATE:" in ics, "Add to calendar downloads an event file")

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
            check(await pg.evaluate("followState().symbols.length + followState().sectors.length + readingState().events.length") == 0, "Start over clears everything, reading too")
            await pg.goto(base + "index.html")
            await pg.wait_for_timeout(600)
            check(await pg.is_visible("#welcomePicker"), "after Start over, Home asks again")
            await pg.goto(base + "company.html")
            await pg.wait_for_timeout(400)
            check(not await pg.is_visible("#followingStrip") and not await pg.is_visible("#followingSection"), "following nothing shows no empty Following strip")
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
