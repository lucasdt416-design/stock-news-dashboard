"""Learning from what you read: kept in the browser, used only by For you, easy to switch off."""

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from pipeline.db import init_db
from pipeline.persist import save_news_items
from pipeline.render import INDEX_TEMPLATE, NEWS_TEMPLATE, SETTINGS_TEMPLATE, SHARED_MOBILE_JS, render_dashboard

READING = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("// ---- Learning from what you read"):SHARED_MOBILE_JS.index("// ---- Following")]


def test_reading_stays_in_the_browser():
    for banned in ("fetch(", "XMLHttpRequest", "sendBeacon", "navigator.", "WebSocket", "document.cookie"):
        assert banned not in READING, banned
    assert re.findall(r"localStorage\.(\w+)\((\w+)", READING) == [("getItem", "READING_KEY"), ("setItem", "READING_KEY")]
    setup = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("function setupLinkUrl"):]
    setup = setup[:setup.index("\n}\n")]
    assert "reading" not in setup.lower(), "the setup link carries follows only"


def test_only_for_you_uses_it():
    assert "const rank = forYou ? readingRanker() : () => ({ boost: 0, often: false });" in NEWS_TEMPLATE
    assert "const rank = readingRanker();" in INDEX_TEMPLATE[INDEX_TEMPLATE.index("function storiesFor"):]
    assert "forgetReadingNow();" in SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("function resetFeed"):], "Start over forgets too"


def test_your_feed_has_the_switch_and_forget():
    assert 'id="learningToggle" data-click="toggleLearning" aria-pressed="true"' in SETTINGS_TEMPLATE
    assert 'id="forgetReadingBtn" data-click="forgetReading"' in SETTINGS_TEMPLATE
    assert "isn’t sent anywhere or put in the setup link" in SETTINGS_TEMPLATE


def test_every_story_row_says_whose_story_it_is(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    save_news_items([{"item_uid": "a", "ticker": "NVDA", "company_name": "NVIDIA", "source": "sec_edgar",
                      "source_label": "SEC EDGAR", "source_type": "regulatory_filing", "headline": "NVDA 10-Q",
                      "summary": "Revenue rose 5%.", "url": "https://www.sec.gov/a", "published_date": "2026-11-01",
                      "form_or_type": "10-Q", "category": "Earnings & Financials", "score": 8.0}], db_path=db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    attrs = 'data-ticker="NVDA" data-source="sec_edgar" data-category="Earnings &amp; Financials"'
    assert attrs in out.read_text(encoding="utf-8")
    company = (out.parent / "company-nvda.html").read_text(encoding="utf-8")
    assert 'data-ticker="NVDA" data-category="Earnings &amp; Financials" data-source="sec_edgar"' in company
    feed = (out.parent / "news.html").read_text(encoding="utf-8")
    assert re.search(r'<article class="news-row[^>]*data-ticker="NVDA"[^>]*data-source="sec_edgar"[^>]*data-category=', feed, re.S)


NODE_HARNESS = r"""
const store = {};
global.localStorage = { getItem: k => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } };
global.document = { addEventListener() {}, dispatchEvent() {} };
global.window = { addEventListener() {}, confirm: () => true };
global.Event = class { constructor(t) { this.type = t; } };
const KNOWN_SYMBOLS = new Set(['NVDA', 'AAPL', 'AMD']);
const STORY_TYPES = { news: 'News articles', releases: 'Company press releases', results: 'Results and reports',
  insider: 'Insider trades', filings: 'Other SEC filings' };
function plural(n, one, many) { return `${n} ${n === 1 ? one : many}`; }
function followReason(t) { return t === 'NVDA' || t === 'AAPL' ? `You follow ${t}` : ''; }
function storyType() { return 'news'; }
READING
const out = {};
const now = Math.floor(Date.now() / 1000);
out.fresh = readingState();
noteRead('NVDA', 'results'); noteRead('NVDA', 'results');
out.dedupe = readingState().events.length;
noteRead('ZZZZ', 'news'); noteRead('NVDA', 'bogus');
out.unknown = readingState().events.length;
out.belowMinimum = readingRanker()('NVDA', 'results').boost;
writeReading({ on: true, events: [
  [now - 3600, 'NVDA', 'results'], [now - 7200, 'NVDA', 'results'], [now - 10800, 'NVDA', 'news'],
  [now - 60 * 86400, 'AAPL', 'news'], [now - 200 * 86400, 'AMD', 'news'], [now - 60, 'AMD', 'page'],
  ['x', 'NVDA', 'news'], [now, 'EVIL', 'news'],
] });
readingMemory = null;  // as on the next page load, which is when stored entries are checked
out.kept = readingState().events.length;
const rank = readingRanker();
out.nvda = rank('NVDA', 'results');
out.aapl = rank('AAPL', 'news');
out.reason = forYouReason('NVDA', [], out.nvda.often);
out.summary = readingSummary();
out.suggest = readButNotFollowed(new Set(['NVDA']), 3);
readingMemory = null;
out.reloaded = readingState().events.length;
toggleLearning();
out.off = readingRanker()('NVDA', 'results').boost;
noteRead('NVDA', 'news');
out.offNoted = readingState().events.length;
toggleLearning();
forgetReading();
out.forgot = readingState().events.length;
const many = []; for (let i = 0; i < 500; i++) many.push([now - i, 'AAPL', 'news']);
store.stockpulse_reading = JSON.stringify({ events: many }); readingMemory = null;
out.capped = readingState().events.length;
store.stockpulse_reading = '{not json'; readingMemory = null;
out.broken = readingState();
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(not shutil.which("node"), reason="needs Node")
def test_reading_maths_in_a_real_engine():
    code = NODE_HARNESS.replace("READING", READING.replace("\\\\", "\\"))
    out = json.loads(subprocess.run(["node", "-e", code], capture_output=True, text=True, check=True).stdout)
    assert out["fresh"] == {"on": True, "events": []}, "on by default, nothing noted"
    assert out["dedupe"] == 1, "a double click counts once"
    assert out["unknown"] == 1, "unknown companies and kinds are ignored"
    assert out["belowMinimum"] == 0, "one read changes nothing"
    assert out["kept"] == 5, "older than 90 days, malformed or unknown entries are dropped"
    assert out["nvda"]["often"] is True and abs(out["nvda"]["boost"] - 2.0) < 0.01, "the cap is 1.5 + 0.5"
    assert 0 < out["aapl"]["boost"] < 1.0 and out["aapl"]["often"] is False, "older reads count less"
    assert out["reason"] == "You follow NVDA · you often read NVDA"
    assert out["summary"]["detail"].startswith("You read most about NVDA, AMD and AAPL, mostly results and reports, then news articles.")
    assert out["suggest"] == [], "a company needs 3 reads before it is suggested"
    assert out["reloaded"] == 5
    assert out["off"] == 0 and out["offNoted"] == 5, "switched off: nothing used, nothing noted"
    assert out["forgot"] == 0
    assert out["capped"] == 400
    assert out["broken"] == {"on": True, "events": []}
