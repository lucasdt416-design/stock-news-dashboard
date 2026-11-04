#!/usr/bin/env python3
"""Attack the rendered site in a real browser, under the real headers.

Builds a database full of hostile text, then loads every page and checks that nothing runs, nothing
is blocked by the CSP during normal use, and every link is safe. Needs no API keys.

Usage:
    python scripts/check_security.py [--out .capture/security]
"""

import argparse
import datetime as dt
import json
import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from capture_site import PAGES, serve  # noqa: E402
from pipeline.db import init_db  # noqa: E402
from pipeline.persist import save_news_items  # noqa: E402
from pipeline.render import render_dashboard  # noqa: E402

XSS = "window.__xss = 1"
HOSTILE_TEXT = [
    f"<img src=x onerror=\"{XSS}\">",
    f"\"><script>{XSS}</script>",
    f"</script><script>{XSS}</script>",
    f"<!--<script>{XSS}",
    f"' onmouseover='{XSS}' x='",
    f"<svg onload={XSS}>",
    "A" * 20000,
    "control\x00\x01\x1f\x7fchars\r\nnew line",
    "{{ 7*7 }}{% raw %}",
]
HOSTILE_URLS = [
    f"javascript:{XSS}",
    f"JaVaScRiPt:{XSS}",
    f" javascript:{XSS}",
    f"data:text/html,<script>{XSS}</script>",
    f"vbscript:{XSS}",
    "httpx://example.com",
    f"https://example.com/\"><script>{XSS}</script>",
]
HOSTILE_QUERIES = [
    f"<img src=x onerror={XSS}>",
    f"\"><script>{XSS}</script>",
    f"javascript:{XSS}",
    "../../etc/passwd",
    "A" * 5000,
]


def hostile_items():
    today = dt.date.today().isoformat()
    items = []
    for i, text in enumerate(HOSTILE_TEXT):
        for j, url in enumerate(HOSTILE_URLS):
            items.append({
                "item_uid": f"hostile-{i}-{j}", "ticker": "NVDA", "company_name": text, "source": "news_media",
                "source_label": text, "source_type": "news", "headline": text, "summary": text, "url": url,
                "published_date": today, "form_or_type": text, "category": text, "score": 9.0 - j * 0.1,
                "score_breakdown": text, "llm_summary": text,
            })
    return items


def link_problems(page):
    return page.evaluate("""() => {
      const out = [];
      document.querySelectorAll('a[href]').forEach(a => {
        const raw = a.getAttribute('href');
        const scheme = (a.protocol || '').toLowerCase();
        if (!['http:', 'https:', 'file:'].includes(scheme)) out.push('unsafe link: ' + raw.slice(0, 60));
        const external = /^https?:/i.test(raw) && a.host !== location.host;
        if (external) {
          const rel = (a.rel || '').toLowerCase();
          if (!rel.includes('noopener') || !rel.includes('noreferrer')) out.push('missing rel: ' + raw.slice(0, 60));
        }
      });
      document.querySelectorAll('*').forEach(el => {
        for (const attr of el.attributes) {
          if (/^on/i.test(attr.name)) out.push('inline handler: ' + attr.name + ' on ' + el.tagName);
          if (attr.name === 'style' && el.dataset.scripted === undefined && attr.value.includes('expression')) out.push('style');
        }
      });
      return out;
    }""")


def run(out):
    os.makedirs(out, exist_ok=True)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        db = os.path.join(tmp, "hostile.db")
        init_db(db)
        save_news_items(hostile_items(), db_path=db)
        site = os.path.join(tmp, "site")
        render_dashboard(output_path=os.path.join(site, "index.html"), db_path=db, performance_data={})
        httpd = serve(site)
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            ctx = browser.new_context(viewport={"width": 1440, "height": 900})
            ctx.route("**/api/lookup*", lambda route: route.fulfill(
                status=200, content_type="application/json",
                body=json.dumps({"found": True, "symbol": "<b>X</b>", "company_name": HOSTILE_TEXT[0],
                                 "resolved_from": HOSTILE_TEXT[1], "price": None, "queried_at": "not a date",
                                 "headlines": [{"headline": HOSTILE_TEXT[0], "url": HOSTILE_URLS[0],
                                                "source": HOSTILE_TEXT[1], "time_ago": HOSTILE_TEXT[5]}]})))
            ctx.add_init_script("""
              document.addEventListener('securitypolicyviolation', e => {
                (window.__violations = window.__violations || []).push(e.violatedDirective + ' ' + e.blockedURI);
              });
            """)
            ctx.add_init_script("try{localStorage.setItem('stockpulse_recently_viewed', " + json.dumps(json.dumps([
                {"symbol": HOSTILE_TEXT[0], "visitedAt": HOSTILE_TEXT[1]}, HOSTILE_TEXT[1], 42, None, {"symbol": "NVDA"},
            ])) + ")}catch(e){}")

            def visit(path, label):
                page = ctx.new_page()
                page.on("pageerror", lambda e: problems.append(f"{label}: page error: {str(e)[:120]}"))
                page.goto(f"{base}/{path}", wait_until="networkidle")
                page.wait_for_timeout(300)
                return page

            def inspect(page, label):
                if page.evaluate("window.__xss === 1"):
                    problems.append(f"{label}: hostile content EXECUTED")
                for item in page.evaluate("window.__violations || []"):
                    problems.append(f"{label}: CSP violation: {item[:120]}")
                problems.extend(f"{label}: {item}" for item in link_problems(page))

            for name, path in PAGES:
                page = visit(path, name)
                inspect(page, name)
                if name == "home":
                    page.screenshot(path=os.path.join(out, "home-hostile.jpg"), type="jpeg", quality=80)
                    box = page.locator("#globalSearchInput")
                    box.click()
                    # An outside query reaches the mocked lookup, whose answer is hostile too.
                    box.press_sequentially("ZZZZ", delay=20)
                    page.wait_for_timeout(700)
                    inspect(page, "home lookup")
                    for query in HOSTILE_QUERIES:
                        box.fill(query)
                        page.wait_for_timeout(450)
                        inspect(page, f"home search {query[:20]}")
                page.close()

            for query in HOSTILE_QUERIES:
                encoded = query.replace("#", "%23")
                for path in (f"company.html?ticker={encoded}", f"news.html?ticker={encoded}", f"news.html?q={encoded}"):
                    page = visit(path, path[:30])
                    inspect(page, path[:30])
                    page.close()

            # The CDN script must load through its integrity check, or charts silently vanish.
            page = visit("analytics.html", "analytics")
            if not page.evaluate("typeof window.Chart === 'function'"):
                problems.append("Chart.js did not load under SRI and CSP")
            page.close()
            browser.close()
        httpd.shutdown()
    return problems


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=".capture/security")
    args = parser.parse_args()
    found = run(args.out)
    unique = sorted(set(found))
    print(f"problems: {len(unique)}")
    for problem in unique[:40]:
        print(" -", problem)
    sys.exit(1 if unique else 0)
