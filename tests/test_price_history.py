"""Long monthly price history: read from Yahoo's answer, kept between runs, written as static files."""

import json
from datetime import date, datetime, timezone

import pytest

from collectors import stock_prices
from collectors.stock_prices import collect_price_history, parse_monthly_history
from pipeline.db import get_db_connection, init_db
from pipeline.prices import get_price_history, save_price_history, write_price_files
from pipeline.render import render_dashboard


def _ts(day):
    """Midnight in New York (UTC-5) on that day, as Yahoo stamps a monthly bar."""
    return int(datetime.strptime(day + " 05:00", "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp())


def _chart(bars, price=12.5, price_day="2026-03-10", kind="EQUITY", currency="USD"):
    """A Yahoo monthly chart answer: bars are (first day of month, adjusted close)."""
    return {
        "meta": {"currency": currency, "instrumentType": kind, "longName": "Test Co", "gmtoffset": -18000,
                 "regularMarketPrice": price, "regularMarketTime": _ts(price_day) + 16 * 3600},
        "timestamp": [_ts(d) for d, _ in bars],
        "indicators": {"quote": [{"close": [v for _, v in bars]}], "adjclose": [{"adjclose": [v for _, v in bars]}]},
    }


BARS = [("2025-12-01", 10.0), ("2026-01-01", 11.0), ("2026-02-01", 12.0), ("2026-03-01", 12.4)]


def test_only_finished_months_are_kept_and_the_latest_price_stands_alone():
    record = parse_monthly_history("TEST", _chart(BARS))
    assert record["months"] == [["2025-12", 10.0], ["2026-01", 11.0], ["2026-02", 12.0]]
    assert record["price"] == 12.5 and record["price_date"] == "2026-03-10"
    assert record["kind"] == "stock" and record["name"] == "Test Co"


def test_yahoos_extra_live_point_is_not_a_month():
    # Yahoo ends the series with a second point for the month in progress, stamped with the time now.
    chart = _chart(BARS)
    chart["timestamp"].append(chart["meta"]["regularMarketTime"])
    chart["indicators"]["adjclose"][0]["adjclose"].append(12.5)
    assert [m for m, _ in parse_monthly_history("TEST", chart)["months"]] == ["2025-12", "2026-01", "2026-02"]


def test_summer_months_are_not_pushed_into_the_month_before():
    # In daylight saving time the bar is stamped 04:00 UTC, an hour earlier than in winter.
    chart = _chart([("2025-07-01", 9.0), ("2025-08-01", 9.5), ("2026-03-01", 12.4)])
    chart["timestamp"][0] -= 3600
    chart["timestamp"][1] -= 3600
    assert [m for m, _ in parse_monthly_history("TEST", chart)["months"]] == ["2025-07", "2025-08"]


def test_a_month_with_no_value_is_left_out_not_filled_in():
    bars = [("2025-12-01", 10.0), ("2026-01-01", None), ("2026-02-01", 12.0), ("2026-03-01", 12.4)]
    assert parse_monthly_history("TEST", _chart(bars))["months"] == [["2025-12", 10.0], ["2026-02", 12.0]]


def test_values_keep_six_significant_figures():
    record = parse_monthly_history("TEST", _chart([("2026-01-01", 0.041804272681474686), ("2026-03-01", 1.0)]))
    assert record["months"] == [["2026-01", 0.0418043]]


def test_funds_are_told_from_stocks():
    assert parse_monthly_history("VOO", _chart(BARS, kind="ETF"))["kind"] == "fund"
    assert parse_monthly_history("VFIAX", _chart(BARS, kind="MUTUALFUND"))["kind"] == "fund"


@pytest.mark.parametrize("chart", [
    _chart(BARS, currency="GBp"),
    _chart(BARS, kind="CRYPTOCURRENCY"),
    _chart(BARS, price=0),
    _chart(BARS, price=None),
    _chart([("2026-01-01", 11.0), ("2025-12-01", 10.0), ("2026-03-01", 12.4)]),
    _chart([("2025-12-01", -1.0), ("2026-03-01", 12.4)]),
    {"meta": {}},
    {},
])
def test_anything_odd_is_refused_rather_than_guessed(chart):
    assert parse_monthly_history("TEST", chart) is None


def test_a_brand_new_listing_has_a_price_and_no_months():
    record = parse_monthly_history("NEW", _chart([("2026-03-01", 12.4)]))
    assert record["months"] == [] and record["price"] == 12.5


def test_one_request_helper_serves_both_daily_and_monthly(monkeypatch):
    calls = []

    def fake(symbol, range_str, interval, timeout=10):
        calls.append((symbol, range_str, interval))
        return _chart(BARS)

    monkeypatch.setattr(stock_prices, "_fetch_chart", fake)
    assert stock_prices.fetch_ticker_monthly_history("TEST")["price"] == 12.5
    stock_prices.fetch_ticker_historical_closes("TEST")
    assert calls == [("TEST", "max", "1mo"), ("TEST", "3mo", "1d")]


def test_collects_the_watchlist_and_spy_and_skips_what_fails(tmp_path):
    watchlist = tmp_path / "w.yaml"
    watchlist.write_text("tickers:\n  - symbol: AAA\n    name: A\n  - symbol: BBB\n    name: B\n", encoding="utf-8")
    asked = []

    def fetch(symbol):
        asked.append(symbol)
        return None if symbol == "BBB" else parse_monthly_history(symbol, _chart(BARS))

    out = collect_price_history(str(watchlist), fetch=fetch, pause=0)
    assert asked == ["AAA", "BBB", "SPY"]
    assert sorted(out) == ["AAA", "SPY"]


def _record(symbol="TEST", months=None, price=12.5, **extra):
    base = {"symbol": symbol, "name": "Test Co", "kind": "stock", "price": price, "price_date": "2026-03-10",
            "months": months if months is not None else [["2026-01", 11.0], ["2026-02", 12.0]]}
    base.update(extra)
    return base


def test_a_good_fetch_replaces_the_whole_series(tmp_path):
    db = str(tmp_path / "t.db")
    save_price_history([_record()], db_path=db, today=date(2026, 3, 10))
    # After a dividend Yahoo rescales every past month, so the old values must not survive.
    rescaled = _record(months=[["2026-01", 10.9], ["2026-02", 11.9], ["2026-03", 12.4]], price=13.0, price_date="2026-04-02")
    assert save_price_history([rescaled], db_path=db, today=date(2026, 4, 2)) == 1
    (stored,) = get_price_history(db)
    assert stored["months"] == [["2026-01", 10.9], ["2026-02", 11.9], ["2026-03", 12.4]]
    assert stored["price"] == {"value": 13.0, "date": "2026-04-02"} and stored["fetched"] == "2026-04-02"
    assert stored["first_month"] == "2026-01" and "demo" not in stored


@pytest.mark.parametrize("bad", [
    None,
    _record(price=0),
    _record(price=-3),
    _record(price=True),
    _record(months=[["2026-02", 12.0], ["2026-01", 11.0]]),
    _record(months=[["2026-13", 12.0]]),
    _record(months=[["2026-01", 0]]),
    _record(months="2026-01"),
    _record(kind="crypto"),
    _record(symbol="bad symbol"),
    _record(price_date="yesterday"),
])
def test_a_bad_reading_leaves_the_last_real_one_with_its_date(tmp_path, bad):
    db = str(tmp_path / "t.db")
    save_price_history([_record()], db_path=db, today=date(2026, 3, 10))
    assert save_price_history([bad], db_path=db, today=date(2026, 3, 11)) == 0
    (stored,) = get_price_history(db)
    assert stored["months"] == [["2026-01", 11.0], ["2026-02", 12.0]]
    assert stored["price"] == {"value": 12.5, "date": "2026-03-10"} and stored["fetched"] == "2026-03-10"


def test_a_ticker_that_did_not_answer_today_keeps_yesterdays_file(tmp_path):
    db = str(tmp_path / "t.db")
    save_price_history([_record("AAA"), _record("BBB")], db_path=db, today=date(2026, 3, 10))
    save_price_history([_record("AAA", price=13.0, price_date="2026-03-11")], db_path=db, today=date(2026, 3, 11))
    assert write_price_files(str(tmp_path / "site"), db) == 2
    folder = tmp_path / "site" / "data" / "prices"
    assert json.loads((folder / "AAA.json").read_text())["fetched"] == "2026-03-11"
    assert json.loads((folder / "BBB.json").read_text())["fetched"] == "2026-03-10"


def test_files_and_index_have_the_planned_shape(tmp_path):
    db = str(tmp_path / "t.db")
    save_price_history([_record("BRK-B"), _record("SPY", kind="fund")], db_path=db, today=date(2026, 3, 10))
    site = tmp_path / "site"
    (site / "data" / "prices").mkdir(parents=True)
    (site / "data" / "prices" / "GONE.json").write_text("{}")
    write_price_files(str(site), db)
    folder = site / "data" / "prices"
    assert sorted(p.name for p in folder.iterdir()) == ["BRK-B.json", "SPY.json", "index.json"]
    assert json.loads((folder / "BRK-B.json").read_text()) == {
        "symbol": "BRK-B", "name": "Test Co", "kind": "stock", "currency": "USD", "first_month": "2026-01",
        "months": [["2026-01", 11.0], ["2026-02", 12.0]], "price": {"value": 12.5, "date": "2026-03-10"},
        "fetched": "2026-03-10",
    }
    index = json.loads((folder / "index.json").read_text())
    assert index == {"symbols": {
        "BRK-B": {"name": "Test Co", "kind": "stock", "price": {"value": 12.5, "date": "2026-03-10"}, "first_month": "2026-01"},
        "SPY": {"name": "Test Co", "kind": "fund", "price": {"value": 12.5, "date": "2026-03-10"}, "first_month": "2026-01"},
    }}


def test_demo_prices_are_marked_as_demo_in_every_file(tmp_path):
    db = str(tmp_path / "t.db")
    save_price_history([_record()], db_path=db, source="demo", today=date(2026, 3, 10))
    write_price_files(str(tmp_path / "site"), db)
    folder = tmp_path / "site" / "data" / "prices"
    assert json.loads((folder / "TEST.json").read_text())["demo"] is True
    assert json.loads((folder / "index.json").read_text())["demo"] is True


def test_the_site_builds_with_no_prices_and_writes_them_when_there_are_some(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    out = tmp_path / "site" / "index.html"
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    assert json.loads((out.parent / "data" / "prices" / "index.json").read_text()) == {"symbols": {}}
    save_price_history([_record("NVDA")], db_path=db)
    render_dashboard(output_path=str(out), db_path=db, performance_data={})
    assert (out.parent / "data" / "prices" / "NVDA.json").exists()


def test_an_older_database_gains_the_table(tmp_path):
    db = str(tmp_path / "t.db")
    init_db(db)
    conn = get_db_connection(db)
    conn.execute("DROP TABLE price_history")
    conn.commit()
    conn.close()
    assert get_price_history(db) == []
