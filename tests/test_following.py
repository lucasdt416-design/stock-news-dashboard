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
    html = _site(tmp_path)["company.html"]
    buttons = re.findall(r'class="follow-btn" type="button" data-click="toggleFollow" data-ticker="([A-Z.\-]+)"', html)
    assert len(set(buttons)) >= 30
    assert html.count("data-follow-mark=") >= 30


def test_follows_stay_in_the_browser():
    # No request carries them anywhere; storage failures are survivable.
    follow_code = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("// ---- Following"):]
    assert "fetch(" not in follow_code and "XMLHttpRequest" not in follow_code and "sendBeacon" not in follow_code
    assert follow_code.count("localStorage.") == 2
    assert follow_code.count("try {") >= 2


def test_setup_links_only_accept_known_symbols_and_never_render_html():
    follow_code = SHARED_MOBILE_JS[SHARED_MOBILE_JS.index("// ---- Following"):]
    assert "filter(s => KNOWN_SYMBOLS.has(s))" in follow_code
    banner = follow_code[follow_code.index("function offerSetupLink"):]
    assert "innerHTML" not in banner, "banner text is set with textContent only"
    assert "acceptSetupLink" in follow_code and "dismissSetupLink" in follow_code, "a link asks before replacing follows"
