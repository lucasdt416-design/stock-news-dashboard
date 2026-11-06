"""The Content-Security-Policy only works if the pages keep to it, and hostile data must stay inert."""

import base64
import hashlib
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pipeline.db import init_db
from pipeline.persist import save_news_items
from pipeline.render import (
    ANALYTICS_TEMPLATE, CALENDAR_TEMPLATE, COMPANY_TEMPLATE, ECONOMIC_TEMPLATE, INDEX_TEMPLATE, NEWS_TEMPLATE,
    _safe_url, _script_json, render_dashboard,
)

TEMPLATES = [INDEX_TEMPLATE, ANALYTICS_TEMPLATE, NEWS_TEMPLATE, CALENDAR_TEMPLATE, ECONOMIC_TEMPLATE, COMPANY_TEMPLATE]
PAGES = ["index", "news", "calendar", "economic", "company", "analytics"]
HOSTILE = '<img src=x onerror="window.__xss=1">'


def _item(uid, text, url):
    return {"item_uid": uid, "ticker": "NVDA", "company_name": text, "source": "news_media", "source_label": text,
            "source_type": "news", "headline": text, "summary": text, "url": url, "published_date": "2026-11-01",
            "form_or_type": text, "category": text, "score": 9.0, "score_breakdown": text, "llm_summary": text}


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("site")
    db = str(tmp / "t.db")
    init_db(db)
    save_news_items([
        _item("a", HOSTILE, "javascript:window.__xss=1"),
        _item("b", '"><script>window.__xss=1</script>', "data:text/html,x"),
        _item("c", "</script><!--<script>" + "A" * 5000, " JaVaScRiPt:window.__xss=1"),
        _item("d", "control\x00\x1f\r\nchars", "https://example.com/ok"),
    ], db_path=db)
    render_dashboard(output_path=str(tmp / "out" / "index.html"), db_path=db, performance_data={})
    return tmp / "out"


def _policy_for(site, page):
    text = (site / "_headers").read_text(encoding="utf-8")
    block = re.search(rf"^/{page}\.html\n  Content-Security-Policy: (.+)$", text, re.M)
    return block.group(1)


class _Tags(HTMLParser):
    """Parses real tags, so escaped text inside an attribute value is not mistaken for markup."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def _tags(html):
    parser = _Tags()
    parser.feed(html)
    return parser.tags


def _strip_scripts(html):
    return re.sub(r"<script\b.*?</script>", "", html, flags=re.S)


@pytest.mark.parametrize("page", PAGES)
def test_pages_have_no_inline_handlers_or_style_attributes(site, page):
    for tag, attrs in _tags((site / f"{page}.html").read_text(encoding="utf-8")):
        assert "style" not in attrs, tag
        assert not [name for name in attrs if name.startswith("on")], (tag, attrs)


def test_scripts_do_not_build_inline_handlers_or_styles():
    for template in TEMPLATES:
        assert not re.search(r'\bon(click|input|change|load|error)=["\'`]', template)
        assert ' style="' not in template


@pytest.mark.parametrize("page", PAGES)
def test_every_inline_block_matches_the_policy_hash(site, page):
    html = (site / f"{page}.html").read_text(encoding="utf-8")
    policy = _policy_for(site, page)
    for pattern, directive in ((r"<script>(.*?)</script>", "script-src"), (r"<style>(.*?)</style>", "style-src")):
        blocks = re.findall(pattern, html, re.S)
        assert blocks
        allowed = re.search(rf"{directive} ([^;]+)", policy).group(1)
        for block in blocks:
            digest = base64.b64encode(hashlib.sha256(block.encode("utf-8")).digest()).decode()
            assert f"'sha256-{digest}'" in allowed


def test_headers_are_strict_and_short_enough_for_cloudflare(site):
    text = (site / "_headers").read_text(encoding="utf-8")
    assert "unsafe-inline" not in text and "unsafe-eval" not in text and "unsafe-hashes" not in text
    for needed in ("X-Content-Type-Options: nosniff", "X-Frame-Options: DENY",
                   "Referrer-Policy: strict-origin-when-cross-origin", "Permissions-Policy:"):
        assert needed in text
    for page in PAGES:
        policy = _policy_for(site, page)
        for directive in ("default-src 'none'", "frame-ancestors 'none'", "base-uri 'none'", "form-action 'none'"):
            assert directive in policy
    assert max(len(line) for line in text.splitlines()) < 2000, "Cloudflare limits a header to 2,000 characters"
    assert "\n/\n" in text and "\n/news\n" in text, "pretty URLs need rules too"


def test_only_pages_with_charts_may_load_the_cdn(site):
    for page in PAGES:
        policy = _policy_for(site, page)
        assert ("cdn.jsdelivr.net" in policy) == (page in ("analytics", "company"))


def test_external_resources_carry_integrity_and_no_web_fonts_load(site):
    for page in PAGES:
        html = (site / f"{page}.html").read_text(encoding="utf-8")
        for tag in re.findall(r"<script[^>]*\ssrc=[^>]*>", html):
            assert 'integrity="sha384-' in tag and 'crossorigin="anonymous"' in tag, tag
        assert "fonts.googleapis.com" not in html
        assert not re.search(r"<link[^>]+stylesheet", html)
        assert "@font-face" not in html
    assert not (site / "assets" / "fonts").exists()


def test_every_action_in_markup_is_in_the_table():
    js = INDEX_TEMPLATE
    table = js[js.index("const PAGE_ACTIONS"):js.index("// Everything inserted through innerHTML")]
    for template in TEMPLATES:
        for kind, name in re.findall(r'data-(click|input|change)="(\w+)"', template):
            assert re.search(rf"\b{name}:", table), f"{kind}: {name}"
    assert "window[" not in table, "actions must be a fixed list, not any global by name"


@pytest.mark.parametrize("url", [
    "javascript:alert(1)", "JaVaScRiPt:alert(1)", " javascript:alert(1)", "java\tscript:alert(1)", "data:text/html,x",
    "vbscript:x", "httpx://example.com", "http-evil:x", "//evil.example", "/relative", "", None, 42,
    'https://example.com/"><script>', "https://exa mple.com", "https://example.com/\x00",
])
def test_safe_url_refuses(url):
    assert _safe_url(url) == "#"
    assert _safe_url(url, "news.html") == "news.html"


@pytest.mark.parametrize("url", ["https://example.com/a?b=1&c=2#d", "http://example.com", "HTTPS://EXAMPLE.COM/x"])
def test_safe_url_allows(url):
    assert _safe_url(url) == url


def test_no_template_puts_an_unchecked_value_in_an_href():
    for template in TEMPLATES:
        for value in re.findall(r'href="\{\{\s*(.+?)\s*\}\}', template):
            assert value.startswith("safe_url("), value


@pytest.mark.parametrize("text", ["</script><script>x</script>", "<!--<script>", "</SCRIPT>", "  "])
def test_script_json_stays_inside_its_block(text):
    out = _script_json({"a": text})
    assert json.loads(out)["a"] == text
    assert "</" not in out and "<!--" not in out and "<script" not in out
    assert " " not in out


@pytest.mark.parametrize("page", PAGES)
def test_hostile_data_is_inert_in_rendered_html(site, page):
    html = (site / f"{page}.html").read_text(encoding="utf-8")
    tags = _tags(html)
    assert not [t for t, attrs in tags if t == "img"], "hostile <img> became a real element"
    assert "<script>window.__xss" not in html
    inline = [t for t, attrs in tags if t == "script" and "src" not in attrs]
    assert len(inline) == 2, "only the theme boot and page scripts may exist"
    for tag, attrs in tags:
        if tag == "a":
            assert not re.match(r"\s*(javascript|data|vbscript):", attrs.get("href") or "", re.I), attrs


def test_all_external_links_are_isolated(site):
    for page in PAGES:
        for tag, attrs in _tags((site / f"{page}.html").read_text(encoding="utf-8")):
            if tag == "a" and re.match(r"https?://", attrs.get("href") or ""):
                assert attrs.get("rel") == "noopener noreferrer", attrs["href"][:100]


def test_search_survives_tickers_stored_as_a_list():
    assert "String(ind.relevant_tickers || '')" in INDEX_TEMPLATE


def test_workflow_requires_generated_headers():
    text = Path(".github/workflows/daily-run.yml").read_text(encoding="utf-8")
    assert 'grep -q "Content-Security-Policy" site/_headers' in text
