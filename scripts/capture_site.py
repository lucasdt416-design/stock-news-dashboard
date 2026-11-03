#!/usr/bin/env python3
"""Screenshot every page at 1440/768/390 px in light and dark, and snapshot its content.

For each page this records console errors, failed requests, horizontal overflow, the DOM ids,
the normalized text, and what each Chart.js canvas draws (type, labels, dataset names), so a
redesign cannot silently drop a chart line or a donut label. Results go to <out>/report.json.

Usage:
    python scripts/capture_site.py --site .capture/site --out .capture/current [--widths 1440,390]
"""

import argparse
import http.server
import json
import os
import socketserver
import threading
from functools import partial

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

PAGES = [
    ("home", "index.html"),
    ("news", "news.html"),
    ("calendar", "calendar.html"),
    ("economic", "economic.html"),
    ("directory", "company.html"),
    ("company", "company.html?ticker=NVDA"),
    ("analytics", "analytics.html"),
]

SNAPSHOT_JS = """() => {
  const clone = document.body.cloneNode(true);
  clone.querySelectorAll('script,style,noscript').forEach(n => n.remove());
  const walker = document.createTreeWalker(clone, NodeFilter.SHOW_TEXT);
  const lines = [];
  while (walker.nextNode()) {
    const t = walker.currentNode.textContent.replace(/\\s+/g, ' ').trim();
    if (t) lines.push(t);
  }
  const charts = [...document.querySelectorAll('canvas')].map(c => {
    const chart = window.Chart && window.Chart.getChart ? window.Chart.getChart(c) : null;
    return {
      id: c.id,
      type: chart ? chart.config.type : null,
      labels: chart ? (chart.data.labels || []).length : 0,
      labelSample: chart ? (chart.data.labels || []).slice(0, 12) : [],
      datasets: chart ? chart.data.datasets.map(d => d.label || '') : [],
    };
  });
  return {
    text: lines,
    ids: [...document.querySelectorAll('[id]')].map(e => e.id).sort(),
    charts,
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    xss: window.__xss === 1,
  };
}"""


TIMEOUT_MS = 120000
LOAD_ATTEMPTS = 3

FULL_PAGE_CSS = """
@media (min-width: 1025px) { .app-sidebar { height: auto !important; position: relative !important; } }
.mobile-bottom-nav { display: none !important; }
.mobile-top-header { position: relative !important; }
"""


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def serve(site):
    socketserver.TCPServer.allow_reuse_address = True
    httpd = socketserver.ThreadingTCPServer(("127.0.0.1", 0), partial(QuietHandler, directory=site))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def load(page, url):
    """Load a page, retrying because fonts and Chart.js come from a CDN and networks drop."""
    for attempt in range(1, LOAD_ATTEMPTS + 1):
        try:
            page.goto(url, wait_until="networkidle")
            return
        except PlaywrightError:
            if attempt == LOAD_ATTEMPTS:
                raise


def capture(site, out, widths, schemes, pages):
    os.makedirs(out, exist_ok=True)
    httpd = serve(site)
    base = f"http://127.0.0.1:{httpd.server_address[1]}"
    report = {"pages": {}, "problems": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for scheme in schemes:
            for width in widths:
                ctx = browser.new_context(
                    viewport={"width": width, "height": 900 if width > 500 else 844},
                    color_scheme=scheme, reduced_motion="reduce",
                    device_scale_factor=1,
                )
                # functions/api/lookup.js only runs on Cloudflare, so answer it the way it answers
                # an unknown ticker. Otherwise every search logs a 404 that production never shows.
                ctx.route("**/api/lookup*", lambda route: route.fulfill(
                    status=200, content_type="application/json",
                    body=json.dumps({"found": False, "message": "No demo data for this ticker."})))
                for name, path in pages:
                    page = ctx.new_page()
                    page.set_default_timeout(TIMEOUT_MS)
                    label = f"{name}-{width}-{scheme}"
                    page.on("console", lambda m, tag=label: report["problems"].append(f"{tag} console.{m.type}: {m.text}")
                            if m.type == "error" else None)
                    page.on("pageerror", lambda e, tag=label: report["problems"].append(f"{tag} pageerror: {e}"))
                    page.on("requestfailed", lambda r, tag=label: report["problems"].append(
                        f"{tag} request failed: {r.url}"))
                    page.on("response", lambda r, tag=label: report["problems"].append(
                        f"{tag} HTTP {r.status}: {r.url.replace(base, '')}") if r.status >= 400 else None)
                    load(page, f"{base}/{path}")
                    page.evaluate("document.fonts.ready")
                    page.wait_for_timeout(500)
                    snap = page.evaluate(SNAPSHOT_JS)
                    if snap["overflow"] > 0:
                        report["problems"].append(f"{label} horizontal overflow: {snap['overflow']}px")
                    if name == "home":
                        check_search(page, label, report)
                    if width < 1100:
                        page.screenshot(path=os.path.join(out, f"{label}-fold.jpg"), type="jpeg", quality=82)
                    # Fixed and sticky chrome lands mid-image in a stitched full-page shot, so lay it out flat.
                    page.add_style_tag(content=FULL_PAGE_CSS)
                    page.screenshot(path=os.path.join(out, f"{label}.jpg"), full_page=True, type="jpeg", quality=82)
                    if label not in report["pages"] and width == widths[0] and scheme == schemes[0]:
                        report["pages"][name] = snap
                    page.close()
                ctx.close()
        browser.close()
    httpd.shutdown()
    with open(os.path.join(out, "report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, indent=1, ensure_ascii=False)
    return report


def check_search(page, label, report):
    """Search must find watchlist companies, and event/news text must stay inert."""
    box = page.locator("#globalSearchInput")
    box.click()
    box.press_sequentially("NVDA", delay=30)
    page.wait_for_timeout(200)
    first_result = page.locator("#liveSearchResults a").first
    if page.locator("#liveSearchResults a").count() == 0 or not first_result.is_visible():
        report["problems"].append(f"{label} search: no visible results for NVDA")
    for query in ("Demo event", "escaping"):
        box.fill(query)
        # The browser fetches a broken <img> and fires onerror asynchronously, so give it time.
        page.wait_for_timeout(600)
        if page.evaluate("window.__xss === 1"):
            report["problems"].append(f"{label} search: dynamic text executed as HTML for '{query}'")
            page.evaluate("window.__xss = 0")
    box.fill("")
    page.evaluate("document.activeElement.blur(); typeof closeSearchDropdown === 'function' && closeSearchDropdown()")
    page.wait_for_timeout(100)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", default=".capture/site")
    parser.add_argument("--out", default=".capture/current")
    parser.add_argument("--widths", default="1440,768,390")
    parser.add_argument("--schemes", default="light,dark")
    parser.add_argument("--pages", default="", help="comma-separated page names; default all")
    args = parser.parse_args()
    wanted = [p for p in PAGES if not args.pages or p[0] in args.pages.split(",")]
    result = capture(os.path.abspath(args.site), os.path.abspath(args.out),
                     [int(w) for w in args.widths.split(",")], args.schemes.split(","), wanted)
    print(f"pages: {len(result['pages'])}  problems: {len(result['problems'])}")
    for problem in result["problems"]:
        print(" -", problem)
