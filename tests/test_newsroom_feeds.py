"""Company newsroom feeds: real feeds only, newest items kept, and people linked to pages, not feed files."""

from pathlib import Path
from unittest.mock import MagicMock, patch
from urllib.parse import urlparse

import yaml

from collectors.company_ir import fetch_ir_feed
from pipeline.db import init_db
from pipeline.render import render_dashboard

WATCHLIST = yaml.safe_load(Path("data/watchlist.yaml").read_text(encoding="utf-8"))["tickers"]


def _rss(*items):
    body = "".join(f"<item><title>{t}</title><link>https://example.com/{i}</link><pubDate>{d}</pubDate></item>"
                   for i, (t, d) in enumerate(items))
    return f'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title>{body}</channel></rss>'.encode()


@patch("collectors.company_ir.urllib.request.urlopen")
def test_a_feed_listed_oldest_first_still_gives_the_newest(mock_urlopen):
    resp = MagicMock()
    resp.read.return_value = _rss(("Old", "Mon, 05 Jan 2026 10:00:00 GMT"), ("Middle", "Mon, 01 Jun 2026 10:00:00 GMT"),
                                  ("New", "Thu, 05 Nov 2026 10:00:00 GMT"), ("Undated", ""))
    resp.__enter__.return_value = resp
    mock_urlopen.return_value = resp
    items = fetch_ir_feed("https://example.com/rss", "BAC", "Bank of America", max_items=2)
    assert [it["title"] for it in items] == ["New", "Middle"]


def test_every_feed_is_a_feed_not_a_web_page():
    """On 2026-11-06, 19 of the first 30 feeds were web pages or dead links."""
    feeds = [c["ir_feed_url"] for c in WATCHLIST if c.get("ir_feed_url")]
    assert len(feeds) >= 60 and len(set(feeds)) == len(feeds)
    for c in WATCHLIST:
        url = c.get("ir_feed_url")
        if not url:
            continue
        assert url.startswith("https://"), c["symbol"]
        assert url not in (c.get("newsroom_url"), c.get("ir_page_url")), f"{c['symbol']}: a page, not a feed"
        assert any(k in url.lower() for k in ("rss", "feed", "xml")), f"{c['symbol']}: {url}"


def test_new_companies_link_to_the_feeds_own_site():
    for c in WATCHLIST:
        if c.get("ir_page_url") and c.get("ir_feed_url"):
            page = urlparse(c["ir_page_url"])
            assert page.path in ("", "/") and page.netloc == urlparse(c["ir_feed_url"]).netloc, c["symbol"]


def test_company_pages_never_link_people_to_a_feed_file(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    visa = (out.parent / "company-v.html").read_text(encoding="utf-8")
    assert '<a href="https://investor.visa.com" target="_blank" rel="noopener noreferrer">Investor site ↗</a>' in visa
    nvda = (out.parent / "company-nvda.html").read_text(encoding="utf-8")
    assert "Newsroom ↗" in nvda
    for c in WATCHLIST:
        if c.get("ir_feed_url"):
            page = (out.parent / f"company-{c['symbol'].lower().replace('.', '-')}.html").read_text(encoding="utf-8")
            assert f'href="{c["ir_feed_url"].replace("&", "&amp;")}"' not in page, c["symbol"]


@patch("collectors.company_ir.urllib.request.urlopen")
def test_an_abandoned_feed_is_reported(mock_urlopen, caplog):
    """Microsoft's old feed still answered, but its newest item was from May 2025."""
    resp = MagicMock()
    resp.read.return_value = _rss(("Ancient", "Wed, 07 May 2025 10:00:00 GMT"))
    resp.__enter__.return_value = resp
    mock_urlopen.return_value = resp
    with caplog.at_level("WARNING"):
        fetch_ir_feed("https://example.com/rss", "MSFT", "Microsoft")
    assert "looks abandoned: its newest item is from 2025-05-07" in caplog.text


def test_feeds_blocked_from_github_are_not_listed():
    """RTX's feed answered here but returned 403 Forbidden to GitHub's servers on 2026-11-07."""
    rtx = next(c for c in WATCHLIST if c["symbol"] == "RTX")
    assert "ir_feed_url" not in rtx and rtx["ir_page_url"] == "https://www.rtx.com"
