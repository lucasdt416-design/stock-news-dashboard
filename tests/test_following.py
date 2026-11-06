"""Following: every page knows the watchlist, offers For you / Everything, and keeps follows local."""

import json
import re
from pathlib import Path

from pipeline.db import init_db
from pipeline.render import SHARED_MOBILE_JS, render_dashboard


def _site(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    return {p.name: p.read_text(encoding="utf-8") for p in out.parent.glob("*.html")}


def test_every_page_knows_which_symbols_can_be_followed(tmp_path):
    for name, html in _site(tmp_path).items():
        m = re.search(r"const KNOWN_SYMBOLS = new Set\((\[.*?\])\);", html)
        assert m, name
        symbols = json.loads(m.group(1))
        assert "NVDA" in symbols and len(symbols) >= 30, name


def test_home_and_feed_offer_both_views(tmp_path):
    site = _site(tmp_path)
    for name in ("index.html", "news.html"):
        assert 'data-view="foryou" data-click="setView"' in site[name], name
        assert 'data-view="all" data-click="setView"' in site[name], name
        assert 'data-click="copySetupLink"' in site[name], name
    assert 'id="topForYou"' in site["index.html"] and 'id="topEverything"' in site["index.html"]


def test_each_company_has_a_follow_button(tmp_path):
    pages = _site(tmp_path)
    assert pages["company.html"].count("data-follow-mark=") >= 30
    company_pages = sorted((tmp_path / "site").glob("company-*.html"))
    assert len(company_pages) >= 30
    for page in company_pages:
        html = page.read_text(encoding="utf-8")
        buttons = re.findall(r'class="follow-btn" type="button" data-click="toggleFollow" data-ticker="([A-Z.\-]+)"', html)
        assert len(buttons) == 1 and page.name == f"company-{buttons[0].lower()}.html", page.name


def test_follows_stay_in_the_browser():
    # No request carries them anywhere; storage failures are survivable.
    follow_code = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("// ---- Following"):]
    assert "fetch(" not in follow_code and "XMLHttpRequest" not in follow_code and "sendBeacon" not in follow_code
    # read, write, and remove on "Start over"; nothing else touches storage
    assert follow_code.count("localStorage.") == 3
    assert follow_code.count("try {") >= 3


def test_setup_links_only_accept_known_symbols_and_never_render_html():
    follow_code = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("// ---- Following"):]
    reader = follow_code[follow_code.index("function readSetupLink"):follow_code.index("function clearSetupHash")]
    assert "KNOWN_SYMBOLS.has" in reader and "KNOWN_SECTORS.has" in reader and "STORY_TYPES" in reader
    banner = follow_code[follow_code.index("function offerSetupLink"):]
    assert "innerHTML" not in banner, "banner text is set with textContent only"
    assert "acceptSetupLink" in follow_code and "dismissSetupLink" in follow_code, "a link asks before replacing follows"


def test_settings_page_offers_every_sector_company_and_story_type(tmp_path):
    from pipeline.render import STORY_TYPES
    html = _site(tmp_path)["settings.html"]
    assert html.count('data-click="toggleSector"') >= 5
    assert len(set(re.findall(r'data-click="toggleFollow" data-ticker="([A-Z.\-]+)"', html))) >= 30
    for key in STORY_TYPES:
        assert f'data-type-toggle="{key}"' in html
    assert 'data-click="copySetupLink"' in html and 'data-click="resetFeed"' in html
    assert "Nothing is sent anywhere" in html


def test_every_page_links_to_your_feed(tmp_path):
    for name, html in _site(tmp_path).items():
        assert 'href="settings.html"' in html, name


def test_first_visit_picker_is_hidden_until_the_script_decides(tmp_path):
    html = _site(tmp_path)["index.html"]
    assert re.search(r'<section class="picker" id="welcomePicker"[^>]*hidden', html), "no-JS visitors never see it"
    assert 'data-click="skipPicker">Show me everything' in html


def test_story_types_sort_the_same_way_in_python_and_the_page():
    from pipeline.render import SHARED_MOBILE_JS, _story_type
    js = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("function storyType"):SHARED_MOBILE_JS.index("function cleanList")]
    cases = [
        ({"source": "sec_edgar", "category": "Insider Transactions"}, "insider"),
        ({"source": "sec_edgar", "category": "Earnings & Financials"}, "results"),
        ({"source": "news_media", "category": "Earnings & Financials"}, "results"),
        ({"source": "sec_edgar", "category": "Leadership & Governance"}, "filings"),
        ({"source": "company_ir", "category": "Product Launches & Technology"}, "releases"),
        ({"source": "news_media", "category": "Company Announcement"}, "news"),
    ]
    for item, expected in cases:
        assert _story_type(item) == expected
    for literal in ("'Insider Transactions'", "'Earnings & Financials'", "'sec_edgar'", "'company_ir'"):
        assert literal in js


def test_trending_ranks_by_this_weeks_important_news_with_real_reasons():
    from datetime import date
    from pipeline.render import _trending
    today = date(2026, 11, 6)
    companies = [{"symbol": "AAA", "name": "A Co", "move_pct": 32.4}, {"symbol": "BBB", "name": "B Co", "move_pct": 2.0},
                 {"symbol": "CCC", "name": "C Co", "move_pct": None}]
    items = (
        [{"ticker": "AAA", "published_date": "2026-11-05", "score": 8.0, "category": "Earnings & Financials"}] * 2
        + [{"ticker": "BBB", "published_date": "2026-11-04", "score": 3.0, "category": "x"}] * 3
        + [{"ticker": "CCC", "published_date": "2026-10-01", "score": 9.0, "category": "x"}] * 5  # too old
        + [{"ticker": "ZZZ", "published_date": "2026-11-05", "score": 9.0, "category": "x"}] * 5  # not on the watchlist
    )
    out = _trending(items, companies, today=today)
    assert [t["symbol"] for t in out] == ["AAA", "BBB"]
    assert out[0]["reason"] == "2 stories this week · Results out Nov 5 · +32% in 3 months"
    assert out[1]["reason"] == "3 stories this week"


def test_home_tabs_come_before_the_welcome(tmp_path):
    html = _site(tmp_path)["index.html"]
    assert html.index('class="view-tabs hero-tabs"') < html.index('class="hero-headline"')
    assert html.count('data-click="setView"') == 2, "one set of tabs on Home"
    assert 'id="heroSince"' in html


def test_followed_companies_get_their_own_lists(tmp_path):
    site = _site(tmp_path)
    assert 'id="followingStrip"' in site["company.html"] and 'id="followingSection"' in site["company.html"]
    assert 'id="settingsFollowing"' in site["settings.html"]
    assert "function followedFirst" in site["company.html"]


def test_last_visit_is_only_a_timestamp_in_this_browser():
    from pipeline.render import INDEX_TEMPLATE
    code = INDEX_TEMPLATE[INDEX_TEMPLATE.index("function readPreviousVisit"):INDEX_TEMPLATE.index("function isNew")]
    assert "stockpulse_last_visit" in code and "try {" in code
    assert "fetch(" not in code
