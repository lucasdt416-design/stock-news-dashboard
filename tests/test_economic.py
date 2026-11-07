"""The Economy page shows real figures and real release dates, or says it has none.

The fixtures in tests/fixtures/economy are copies of the real sources saved on 2026-11-06: FRED's
download files, the Fed's meeting calendar, the BLS release calendar and the EIA's schedule.
"""

import datetime
import inspect
import os
import re
import sqlite3

import pytest

from pipeline import economic
from pipeline.economic import (
    INDICATORS,
    collect_economic_indicators,
    collect_economic_releases,
    generate_economic_synthesis,
    get_upcoming_economic_events,
    init_economic_schema,
    parse_bls_dates,
    parse_eia_dates,
    parse_fomc_dates,
    parse_fred_csv,
    snapshot_fetch,
)
from pipeline.persist import get_economic_indicators
from pipeline.render import render_dashboard

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures", "economy")
SAVED_ON = datetime.date(2026, 11, 6)
D = datetime.date


def fetch():
    return snapshot_fetch(FIXTURES)


def broken(url):
    raise OSError("no network")


def by_id(cards):
    return {c["indicator_id"]: c for c in cards}


def test_nothing_is_typed_in():
    source = inspect.getsource(economic)
    assert not hasattr(economic, "FALLBACK_INDICATORS")
    assert "consensus" not in source.lower()
    figure = re.compile(r"\d\.\d|\d\s*%|\$\s*\d|\d\s*(?:bp|K|M|bbl)\b")
    for spec in INDICATORS:
        assert not figure.search(" ".join(str(v) for v in spec.values())), spec["indicator_id"]
    for meta in economic.RELEASES.values():
        assert not figure.search(" ".join(meta.values()))


def test_figures_match_the_saved_fred_files(tmp_path):
    cards = by_id(collect_economic_indicators(db_path=str(tmp_path / "e.db"), fetch=fetch(), today=SAVED_ON))
    assert list(cards) == ["interest_rates", "treasury_10y", "inflation", "crude_oil", "unemployment"]

    rates = cards["interest_rates"]
    assert rates["formatted_value"] == "3.75–4.00% (effective rate 3.88%)"
    assert rates["as_of"] == "Nov 6, 2026" and rates["change_text"] == "Unchanged since Oct 9"

    ten = cards["treasury_10y"]
    assert ten["formatted_value"] == "4.84%" and ten["as_of"] == "Nov 5, 2026"
    assert ten["change_direction"] == "down" and ten["change_text"] == "−0.38 pts since Oct 8"

    # CPI index 336.940 in Sep 2026 against 324.800 in Sep 2025 (saved file) is a 3.7% rise.
    cpi = cards["inflation"]
    assert cpi["formatted_value"] == "3.7%" and cpi["as_of"] == "September 2026"
    assert cpi["change_text"] == "+0.3 pts since August"
    assert cpi["history"][-1]["value"] == 3.7, "the chart ends on the figure shown beside it"

    oil = cards["crude_oil"]
    assert oil["formatted_value"] == "$99.64 (a barrel)" and oil["as_of"] == "Nov 3, 2026"
    assert oil["change_text"] == "+$3.40 since Oct 6"

    jobs = cards["unemployment"]
    assert jobs["formatted_value"] == "4.1%" and jobs["as_of"] == "October 2026"
    assert jobs["change_text"] == "−0.1 pts since September"

    for card in cards.values():
        assert len(card["history"]) == 13
        assert card["source_url"] == f"https://fred.stlouisfed.org/series/{card['series_id']}"


def test_cpi_is_the_twelve_month_change_of_the_index():
    points = dict(parse_fred_csv(fetch()("https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCNS&cosd=x"), "CPIAUCNS"))
    assert round((points[D(2026, 9, 1)] / points[D(2025, 9, 1)] - 1) * 100, 1) == 3.7


def test_a_page_that_is_not_the_series_is_rejected():
    with pytest.raises(ValueError):
        parse_fred_csv("<!DOCTYPE html><html>Not found</html>", "DGS10")
    with pytest.raises(ValueError):
        parse_fred_csv("observation_date,DGS2\n2026-11-05,3.9\n", "DGS10")
    assert parse_fred_csv("observation_date,DGS10\n2026-11-04,\n2026-11-05,4.84\n2026-11-06,.\n", "DGS10") == [(D(2026, 11, 5), 4.84)]


def test_an_unreadable_source_keeps_the_last_real_reading(tmp_path):
    db = str(tmp_path / "e.db")
    collect_economic_indicators(db_path=db, fetch=fetch(), today=SAVED_ON)
    assert collect_economic_indicators(db_path=db, fetch=broken) == []
    kept = by_id(get_economic_indicators(db_path=db))
    assert kept["treasury_10y"]["formatted_value"] == "4.84%" and kept["treasury_10y"]["as_of"] == "Nov 5, 2026"


def test_with_no_reading_ever_there_is_nothing_to_show(tmp_path):
    db = str(tmp_path / "e.db")
    assert collect_economic_indicators(db_path=db, fetch=broken) == []
    assert get_economic_indicators(db_path=db) == []


def test_old_typed_in_rows_are_never_shown(tmp_path):
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE economic_indicators (indicator_id TEXT PRIMARY KEY, name TEXT NOT NULL,
        series_id TEXT NOT NULL, category TEXT NOT NULL, current_value REAL NOT NULL, formatted_value TEXT NOT NULL,
        unit TEXT NOT NULL, previous_value REAL, change_value REAL, change_direction TEXT,
        observation_date TEXT NOT NULL, updated_at TEXT NOT NULL, context_note TEXT, relevant_tickers TEXT NOT NULL,
        history_json TEXT, ai_synthesis TEXT)""")
    conn.execute("INSERT INTO economic_indicators VALUES ('treasury_10y','10Y','DGS10','x',4.28,'4.28%','%',4.23,0.05,"
                 "'up','2026-09-11','2026-09-11','','JPM','[]','')")
    conn.commit()
    assert get_economic_indicators(db_path=db) == [], "a table from before the change is all placeholders"
    init_economic_schema(conn)
    assert conn.execute("SELECT COUNT(*) FROM economic_indicators").fetchone()[0] == 0
    conn.close()


def T(y, m, d, hh, mm):
    return datetime.datetime(y, m, d, hh, mm)


def test_fed_meeting_dates():
    dates = parse_fomc_dates(fetch()(economic.FOMC_URL))
    days = [D(2026, 1, 28), D(2026, 3, 18), D(2026, 4, 29), D(2026, 6, 17),
            D(2026, 7, 29), D(2026, 9, 16), D(2026, 10, 28), D(2026, 12, 9)]
    assert [d for d in dates if d.year == 2026] == [datetime.datetime.combine(d, datetime.time(14, 0)) for d in days]
    assert T(2027, 1, 27, 14, 0) in dates and len(dates) == 16
    across = ('2028 FOMC Meetings <div class="fomc-meeting__month"><strong>Oct/Nov</strong></div>'
              '<div class="fomc-meeting__date">31-1</div> <div class="fomc-meeting__month"><strong>March</strong></div>'
              '<div class="fomc-meeting__date">9 (notation vote)</div>')
    assert parse_fomc_dates(across) == [T(2028, 11, 1, 14, 0)]


def test_bls_release_dates():
    dates = parse_bls_dates(fetch()(economic.BLS_ICS_URL))
    assert T(2026, 11, 6, 8, 30) in dates["jobs"] and T(2026, 12, 4, 8, 30) in dates["jobs"]
    assert T(2026, 11, 10, 8, 30) in dates["cpi"] and T(2026, 12, 10, 8, 30) in dates["cpi"]
    assert all(d.date() != D(2026, 11, 7) for d in dates["jobs"]), "Employment Situation of Veterans is a different release"


def test_eia_uses_wednesdays_and_the_listed_exceptions():
    page = fetch()(economic.EIA_SCHEDULE_URL)
    dates = parse_eia_dates(page, SAVED_ON)
    assert T(2026, 11, 12, 12, 0) in dates, "Veterans Day moves it to Thursday at noon"
    assert all(d.date() != D(2026, 11, 11) for d in dates)
    assert T(2026, 11, 18, 10, 30) in dates and all(d.year == 2026 for d in dates)
    assert parse_eia_dates(page, D(2027, 3, 1)) == [], "no dates for a year the EIA hasn't listed holidays for"
    with pytest.raises(ValueError):
        parse_eia_dates("<html>moved</html>", SAVED_ON)


def test_next_release_of_each_kind(tmp_path):
    db = str(tmp_path / "e.db")
    assert collect_economic_releases(db_path=db, fetch=fetch(), today=SAVED_ON) == {"fomc": 16, "jobs": 12, "cpi": 12, "eia": 8}
    early = get_upcoming_economic_events(db_path=db, now=T(2026, 11, 6, 7, 0))
    assert [(e["event_id"], e["date"], e["time_text"]) for e in early] == [
        ("jobs", "2026-11-06", "8:30 a.m. ET"), ("cpi", "2026-11-10", "8:30 a.m. ET"),
        ("eia", "2026-11-12", "12:00 p.m. ET"), ("fomc", "2026-12-09", "2:00 p.m. ET")]
    later = get_upcoming_economic_events(db_path=db, now=T(2026, 11, 6, 8, 30))
    assert ("jobs", "2026-12-04") in [(e["event_id"], e["date"]) for e in later], "a report that is out drops off"
    for e in later:
        assert e["title"] and e["authority"] and e["about"] and e["source_url"].startswith("https://www.")
    collect_economic_releases(db_path=db, fetch=broken, today=SAVED_ON)
    assert len(get_upcoming_economic_events(db_path=db, now=T(2026, 11, 6, 7, 0))) == 4, "an unreadable calendar keeps its dates"
    assert get_upcoming_economic_events(db_path=db, now=T(2029, 1, 1, 0, 0)) == []


def test_the_plain_line_uses_only_the_figure_it_was_given():
    for spec in INDICATORS:
        line = generate_economic_synthesis(spec["indicator_id"], spec["name"], "4.84% (effective rate 3.88%)", "down",
                                           -0.38, ["JPM", "BAC"], api_key="")
        assert "4.84%" in line and "JPM, BAC" in line
        assert re.findall(r"\d+\.\d+", line) == ["4.84"], line
    assert "rose to" in generate_economic_synthesis("crude_oil", "Oil", "$99.64 (a barrel)", "up", 3.4, [], api_key="")


def test_render_economic_page(tmp_path):
    db = str(tmp_path / "e.db")
    site = tmp_path / "site"
    collect_economic_indicators(db_path=db, fetch=fetch(), today=SAVED_ON)
    collect_economic_releases(db_path=db, fetch=fetch(), today=SAVED_ON)
    soon = datetime.date.today() + datetime.timedelta(days=3)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM economic_releases WHERE kind = 'fomc'")
    conn.execute("INSERT INTO economic_releases VALUES ('fomc', ?, '14:00', 'now')", (soon.isoformat(),))
    conn.commit()
    conn.close()
    render_dashboard(output_path=str(site / "index.html"), db_path=db, performance_data={})
    page = (site / "economic.html").read_text(encoding="utf-8")

    assert "3.75–4.00%" in page and "(effective rate 3.88%)" in page
    assert "As of September 2026" in page and "−0.38 pts since Oct 8" in page
    assert 'href="https://fred.stlouisfed.org/series/DGS10"' in page
    assert "2:00 p.m. ET · The Fed announces" in page
    assert "Fed interest rate decision" in page and 'href="https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"' in page
    for gone in ("Expected:", "Steady", "4.28%", "76.50", "It is a fixed list"):
        assert gone not in page, gone
    assert "Why it matters" in page and "renderEconSparklines" in page


def test_render_with_nothing_read_says_so(tmp_path):
    db = str(tmp_path / "e.db")
    collect_economic_indicators(db_path=db, fetch=broken)
    collect_economic_releases(db_path=db, fetch=broken)
    render_dashboard(output_path=str(tmp_path / "site" / "index.html"), db_path=db, performance_data={})
    page = (tmp_path / "site" / "economic.html").read_text(encoding="utf-8")
    assert "No figures yet." in page and "No dates to show." in page
    assert "economic-card" not in page.split("economicCardsGrid", 1)[1].split("</div>", 1)[0]


def test_unemployment_is_described_as_bls_defines_it():
    note = by_id(INDICATORS)["unemployment"]["context_note"]
    assert "labor force" in note and "working or looking for work" in note
