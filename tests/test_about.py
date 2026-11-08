"""The About page: why the site exists, not advice, and a privacy note that matches what the code does."""

import re
from urllib.parse import urlparse

from pipeline.db import init_db
from pipeline.render import ABOUT_TEMPLATE, CHART_JS_URL, NAVIGATION_LAYOUT_HTML, SHARED_MOBILE_JS, render_dashboard


def _templates():
    from pipeline import render
    return {name: value for name, value in vars(render).items() if name.endswith("_TEMPLATE") and isinstance(value, str)}


def test_linked_once_from_the_menu_not_a_footer_on_every_page():
    assert NAVIGATION_LAYOUT_HTML.count('href="about.html"') == 1
    assert 'href="about.html"' in NAVIGATION_LAYOUT_HTML[NAVIGATION_LAYOUT_HTML.index('class="sidebar-footer"'):]
    bottom = NAVIGATION_LAYOUT_HTML[NAVIGATION_LAYOUT_HTML.index('class="mobile-bottom-nav"'):]
    assert "about.html" not in bottom
    for name, template in _templates().items():
        assert "<footer" not in template, name


def test_it_says_it_is_not_advice():
    assert "Not investment advice" in ABOUT_TEMPLATE
    assert "It doesn't claim the story caused the move." in ABOUT_TEMPLATE


def test_the_privacy_note_matches_the_code():
    code = "".join(_templates().values()) + SHARED_MOBILE_JS
    assert "document.cookie" not in code, "the page says there are no cookies"
    for tracker in ("googletagmanager", "google-analytics", "plausible", "segment.com", "facebook.net"):
        assert tracker not in code, tracker
    # Every outside host a page can load from is named on the About page.
    hosts = {urlparse(u).netloc for u in re.findall(r'src="(https://[^"]+)"', code)} | {urlparse(CHART_JS_URL).netloc}
    named = {"cdn.jsdelivr.net": "jsDelivr"}
    for host in hosts:
        assert named.get(host) and named[host] in ABOUT_TEMPLATE, host
    # What is kept in the browser is what the page lists.
    keys = set(re.findall(r"stockpulse_[a-z_]+", code))
    assert keys <= {"stockpulse_follow", "stockpulse_reading", "stockpulse_theme", "stockpulse_recently_viewed",
                    "stockpulse_last_visit", "stockpulse_prev_visit", "stockpulse_probe"}, keys - {"x"}
    for words in ("companies you follow", "what you've read", "your theme", "viewed recently"):
        assert words in ABOUT_TEMPLATE, words


def test_every_source_is_credited():
    for source in ("EDGAR", "Finnhub", "Yahoo Finance", "FRED", "Bureau of Labor Statistics",
                   "Energy Information Administration", "Gemini", "newsroom feed"):
        assert source in ABOUT_TEMPLATE, source


def test_the_about_page_renders(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    about = (out.parent / "about.html").read_text(encoding="utf-8")
    assert '<a class="sidebar-about active" href="about.html"' in about
    assert '<a class="sidebar-about" href="about.html"' in out.read_text(encoding="utf-8")


def test_it_links_to_the_code():
    assert 'href="https://github.com/lucasdt416-design/stock-news-dashboard"' in ABOUT_TEMPLATE
