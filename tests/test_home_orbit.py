"""Home: the ring is real links, with a static fallback, and search stays wired up safely."""

import re
from datetime import date
from pathlib import Path

from pipeline.db import init_db
from pipeline.render import INDEX_TEMPLATE, _heat_class, _next_earnings, _orbit_companies, _sparkline_points, render_dashboard, _figures_html, _story_text

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


def _perf(*moves):
    series = [{"close": 10.0}, {"close": 12.0}, {"close": 11.0}]
    return {"companies": {sym: {"target": {"total_pct_change": pct, "series": series}} for sym, pct in moves}}


def _render_with(tmp_path, performance_data):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data=performance_data)
    return Path(out).read_text(encoding="utf-8")


def test_home_says_welcome_with_the_slogan(tmp_path):
    html = _render_with(tmp_path, {})
    assert ">Welcome!</h1>" in html
    assert "We keep you informed about the stocks you follow." in html


def test_no_price_data_draws_no_moves_rather_than_fake_zeros(tmp_path):
    html = _render_with(tmp_path, {})
    for drawn in ('class="heat-tile', 'class="heat-heading', 'class="orbit-spark', 'class="orbit-note', "+0.0%"):
        assert drawn not in html, drawn
    assert "orbit-fact" in html, "chips fall back to the story count"


def test_map_runs_best_to_worst_and_counts_up_and_down(tmp_path):
    html = _render_with(tmp_path, _perf(("NVDA", -20.0), ("AAPL", 14.3), ("MSFT", 0.0), ("KO", 30.0)))
    assert re.findall(r'heat-tile [^"]+" href="company\.html\?ticker=([A-Z]+)"', html) == ["KO", "AAPL", "MSFT", "NVDA"]
    assert ">2 up, 1 down</h2>" in html
    assert "+14.3%" in html and "-20.0%" in html
    assert 'class="orbit-move tone-down">-20.0%' in html


def test_sparkline_fits_its_box_and_ignores_bad_points():
    points = _sparkline_points([{"close": c} for c in range(1, 67)] + [{"close": "x"}, None])
    pairs = [tuple(map(float, p.split(","))) for p in points.split()]
    assert len(pairs) <= 25
    assert pairs[0][0] == 0 and pairs[-1][0] == 100
    assert pairs[0][1] == 28 and pairs[-1][1] == 0, "the first and last closes both survive thinning"
    assert all(0 <= y <= 28 for _, y in pairs)
    assert _sparkline_points([{"close": 1}]) == "" and _sparkline_points(None) == ""
    assert "nan" not in _sparkline_points([{"close": 5}, {"close": 5}])


def test_heat_steps():
    cases = {0.0: "heat-n", 1.9: "heat-n", -1.9: "heat-n", 2: "heat-u1", 8: "heat-u2", 16: "heat-u3",
             -2: "heat-d1", -8: "heat-d2", -42.6: "heat-d3"}
    for pct, expected in cases.items():
        assert _heat_class(pct) == expected, pct


def test_story_text_is_the_sources_own_words():
    item = {"summary": "Nxera gets US$100 million upfront.", "llm_summary": "Antitrust regulatory scrutiny."}
    assert _story_text(item) == "Nxera gets US$100 million upfront."


def test_filings_with_only_a_reference_show_nothing_rather_than_filler():
    assert _story_text({"summary": "Official SEC submission (8-K). Accession: 1 | Report Period: 2026-11-04"}) == ""
    assert _story_text({"summary": None}) == ""


def test_cut_off_text_ends_cleanly_without_losing_figures():
    whole = "McDonald's posted a third-quarter beat that lifted its shares."
    assert _story_text({"summary": f"{whole} Tokyo, Ja..."}) == whole
    kept = _story_text({"summary": f"{whole} It also raised its dividend to $1.9..."})
    assert kept.endswith("$1.9…")
    assert _story_text({"summary": "Too short to trim. Rest of it..."}) == "Too short to trim. Rest of it…"
    assert _story_text({"summary": "plus royalties.NXE0033744 is a candidate"}).startswith("plus royalties. NXE")


def test_figures_are_marked_and_everything_else_stays_escaped():
    html = str(_figures_html('Up 12.5% on $1.37 billion, 3 million units. <img src=x onerror="a()"> 39 items'))
    for figure in ("12.5%", "$1.37 billion", "3 million"):
        assert f'<strong class="fig">{figure}</strong>' in html
    assert "<img" not in html and "&lt;img" in html
    assert html.count("<strong") == 3, "HTML entities and plain counts are not figures"


def test_stories_render_their_figures_and_never_the_template_takeaway(tmp_path):
    from pipeline.db import get_db_connection
    from pipeline.persist import save_news_items
    db = str(tmp_path / "t.db")
    init_db(db)
    save_news_items([{"item_uid": "u1", "ticker": "NVDA", "company_name": "NVIDIA", "source": "news_media",
                      "source_type": "news", "source_label": "Yahoo", "category": "Other", "score": 9.0,
                      "headline": "Big deal", "summary": "Nvidia pays $5 billion.", "llm_summary": "Antitrust scrutiny.",
                      "url": "https://example.com/a", "published_date": "2026-11-01"}], db_path=db)
    get_db_connection(db).close()
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    for page in ("index", "news", "company"):
        html = (tmp_path / "site" / f"{page}.html").read_text(encoding="utf-8")
        body = html[:html.rindex("<script>")]
        assert '<strong class="fig">$5 billion</strong>' in body, page
        assert "Antitrust scrutiny." not in body, page
