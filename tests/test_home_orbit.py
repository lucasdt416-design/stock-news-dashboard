"""Home: the ring is real links, with a static fallback, and search stays wired up safely."""

import re
from datetime import date
from pathlib import Path

from pipeline.db import init_db
from pipeline.render import INDEX_TEMPLATE, _next_earnings, _orbit_companies, render_dashboard

REQUIRED_IDS = ("globalSearchInput", "searchDropdown", "defaultDropdownContent", "liveSearchResults",
                "recentlyViewedSection", "recentlyViewedGrid", "heroOrbitStage")


def _function_body(name):
    start = INDEX_TEMPLATE.index(f"function {name}(")
    depth, i = 0, INDEX_TEMPLATE.index("{", start)
    for j in range(i, len(INDEX_TEMPLATE)):
        depth += {"{": 1, "}": -1}.get(INDEX_TEMPLATE[j], 0)
        if depth == 0:
            return INDEX_TEMPLATE[i:j]
    raise AssertionError(name)


def _render(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    return Path(out).read_text(encoding="utf-8")


def test_required_ids_and_real_links_are_in_the_html(tmp_path):
    html = _render(tmp_path)
    for dom_id in REQUIRED_IDS:
        assert f'id="{dom_id}"' in html
    links = re.findall(r'class="orbit-chip" href="company\.html\?ticker=([A-Z.\-]+)"', html)
    assert len(links) >= 30, "every watchlist company stays reachable from the list"
    assert 'href="company.html"' in html, "Browse all companies"
    assert 'hero-orbit-stage orbit-static"' in html, "no-JS visitors must get the static grid"


def test_only_twelve_chips_show_before_the_script_runs(tmp_path):
    html = _render(tmp_path)
    slots = re.findall(r'<li class="orbit-slot"[^>]*>', html)
    assert len([s for s in slots if " hidden" not in s]) == 12


def test_search_functions_do_not_call_each_other():
    assert "handleSearchType(" not in _function_body("openSearchDropdown")
    assert "openSearchDropdown(" not in _function_body("handleSearchType")


def test_input_is_handled_once():
    assert "oninput=" not in INDEX_TEMPLATE[INDEX_TEMPLATE.index("globalSearchInput"):][:400]
    assert INDEX_TEMPLATE.count("handleSearchType(e.target.value)") == 1


def test_motion_respects_limits():
    assert "prefers-reduced-motion: reduce" in INDEX_TEMPLATE
    assert "? 40 : 120" in INDEX_TEMPLATE, "particle caps"
    assert "visibilitychange" in INDEX_TEMPLATE
    assert "'wheel'" not in INDEX_TEMPLATE and '"wheel"' not in INDEX_TEMPLATE, "must not hijack page scroll"
    assert "touch-action: pan-y" in INDEX_TEMPLATE or "touch-action: pan-y" in _css()


def _css():
    from pipeline.render import SHARED_CSS
    return SHARED_CSS


def test_no_decorative_effects_in_the_stylesheet():
    css = _css()
    for banned in ("backdrop-filter", "background-clip: text", "radial-gradient", "conic-gradient"):
        assert banned not in css, banned


def test_recently_viewed_from_storage_is_checked_against_the_watchlist():
    body = _function_body("readRecentlyViewed")
    assert "known.has(symbol)" in body
    assert "Array.isArray(stored)" in body
    assert "Number.isFinite" in body


def test_orbit_ranks_by_top_story_and_counts_only_recent_stories():
    companies = [{"symbol": s, "name": s} for s in ("AAA", "BBB", "CCC", "DDD")]
    today = date(2026, 6, 10)
    items = [
        {"ticker": "BBB", "score": 9.0, "published_date": "2026-06-09"},
        {"ticker": "BBB", "score": 4.0, "published_date": "2026-01-01"},
        {"ticker": "AAA", "score": 6.0, "published_date": "2026-06-10"},
        {"ticker": "CCC", "score": 9.0, "published_date": "2026-06-08"},
        {"ticker": "CCC", "score": 8.0, "published_date": "2026-06-07"},
        {"ticker": "CCC", "score": 8.0, "published_date": "not a date"},
    ]
    ranked = _orbit_companies(items, companies, today=today)
    assert [c["symbol"] for c in ranked] == ["CCC", "BBB", "AAA", "DDD"]
    assert ranked[0]["new_count"] == 2
    assert ranked[1]["new_count"] == 1
    assert ranked[3]["top_score"] is None


def test_next_earnings_skips_other_events():
    events = [{"event_type": "Shareholder Meeting", "headline": "AGM"},
              {"event_type": "Earnings Call", "headline": "Q2", "ticker": "X"}]
    assert _next_earnings(events)["ticker"] == "X"
    assert _next_earnings(events[:1]) is None
