"""Unit tests for the corporate calendar engine, Finnhub structured earnings, and EDGAR 10-Q/10-K capture."""

import datetime
import os
import sqlite3
import tempfile
from unittest.mock import MagicMock, patch
import pytest

from collectors.earnings_calendar import (
    collect_finnhub_earnings_calendar,
    format_hour_timing,
    format_revenue,
)
from collectors.edgar import parse_submissions
from pipeline.calendar import (
    build_forthcoming_calendar,
    calculate_relative_badge,
    calculate_sec_filing_deadlines,
    clean_and_extract_event_dates,
)
from pipeline.db import init_db


def test_format_revenue():
    assert format_revenue(108129157692) == "$108.13B"
    assert format_revenue(950000000) == "$950.0M"
    assert format_revenue(2500000000000) == "$2.50T"
    assert format_revenue(None) == "N/A"
    assert format_revenue(0) == "N/A"


def test_format_hour_timing():
    assert format_hour_timing("bmo") == "Before Market Open"
    assert format_hour_timing("amc") == "After Market Close"
    assert format_hour_timing("dmh") == "During Market Hours"
    assert format_hour_timing("") == "Scheduled"
    assert format_hour_timing(None) == "Scheduled"


def test_calculate_relative_badge():
    today = datetime.date(2026, 9, 14)
    assert calculate_relative_badge("2026-09-14", today=today) == "Today"
    assert calculate_relative_badge("2026-09-15", today=today) == "Tomorrow"
    assert calculate_relative_badge("2026-09-18", today=today) == "In 4 days"
    assert calculate_relative_badge("2026-09-24", today=today) == "In 1 week"
    assert calculate_relative_badge("2026-10-05", today=today) == "In 3 weeks"
    assert calculate_relative_badge("2026-11-17", today=today) == "In ~2 months"


@patch("collectors.earnings_calendar.fetch_ticker_earnings_calendar")
def test_collect_finnhub_earnings_calendar(mock_fetch):
    mock_fetch.return_value = [
        {
            "symbol": "NVDA",
            "date": "2026-11-17",
            "hour": "amc",
            "quarter": 3,
            "year": 2027,
            "epsEstimate": 2.4659,
            "epsActual": None,
            "revenueEstimate": 108129157692,
            "revenueActual": None,
        }
    ]

    watchlist = [{"symbol": "NVDA", "name": "NVIDIA Corporation"}]
    today = datetime.date(2026, 9, 14)

    events = collect_finnhub_earnings_calendar(
        watchlist=watchlist,
        api_key="test_token",
        days_forward=120,
        delay_seconds=0,
        today=today,
    )

    assert len(events) == 1
    ev = events[0]
    assert ev["ticker"] == "NVDA"
    assert ev["event_date"] == "2026-11-17"
    assert ev["event_type"] == "Earnings Call / Results"
    assert ev["source_type"] == "SOURCED"
    assert "Q3 2027" in ev["headline"]
    assert "After Market Close" in ev["headline"]
    assert "$2.47" in ev["details"]
    assert "$108.13B" in ev["details"]


def test_edgar_parse_submissions_guarantees_10q_and_10k():
    """Verify that when >30 Form 4s precede 10-Q/10-K, both 10-Q and 10-K are still captured."""
    num_form4s = 50
    forms = ["4"] * num_form4s + ["10-Q", "10-K"]
    accession_numbers = [f"0000000000-26-{i:06d}" for i in range(len(forms))]
    filing_dates = ["2026-09-01"] * len(forms)
    report_dates = ["2026-06-30"] * len(forms)
    acceptance_dts = ["2026-09-01T16:00:00.000Z"] * len(forms)
    primary_docs = [f"doc_{i}.xml" for i in range(len(forms))]
    primary_descs = [f"Form {f}" for f in forms]

    mock_data = {
        "name": "NVIDIA Corporation",
        "cik": "1045810",
        "filings": {
            "recent": {
                "accessionNumber": accession_numbers,
                "filingDate": filing_dates,
                "reportDate": report_dates,
                "acceptanceDateTime": acceptance_dts,
                "form": forms,
                "primaryDocument": primary_docs,
                "primaryDocDescription": primary_descs,
            }
        },
    }

    # max_items = 30, but 10-Q is at index 50 and 10-K is at index 51
    parsed = parse_submissions(mock_data, ticker="NVDA", max_items=30)

    assert len(parsed) <= 30
    forms_captured = [p["form"] for p in parsed]
    assert "10-Q" in forms_captured, "Latest 10-Q must be guaranteed in parsed output"
    assert "10-K" in forms_captured, "Latest 10-K must be guaranteed in parsed output"


def test_calculate_sec_filing_deadlines_from_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        # Insert a 10-Q filing record with report date
        conn.execute(
            """
            INSERT INTO news_items (
                item_uid, ticker, company_name, source, source_label, source_type,
                headline, summary, url, published_date, form_or_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "uid_test_10q",
                "NVDA",
                "NVIDIA Corporation",
                "sec_edgar",
                "SEC EDGAR",
                "regulatory_filing",
                "NVIDIA Files Quarterly Financial Report (10-Q)",
                "Official SEC submission (10-Q). Accession: 0001045810-26-000010 | Report Period: 2026-06-30",
                "https://sec.gov/doc",
                "2026-08-26",
                "10-Q",
            ),
        )
        conn.commit()

        today = datetime.date(2026, 9, 14)
        deadlines = calculate_sec_filing_deadlines(conn, today=today)

        assert len(deadlines) == 1
        dl = deadlines[0]
        assert dl["ticker"] == "NVDA"
        assert dl["source_type"] == "ESTIMATED_RULE"
        # Q3 period ends Sept 30, + 40 days = Nov 9
        assert dl["event_date"] == "2026-11-09"
        assert "40d Rule" in dl["headline"]
        conn.close()


@patch("pipeline.calendar.collect_finnhub_earnings_calendar")
def test_build_forthcoming_calendar_integration(mock_finnhub):
    today = datetime.date(2026, 9, 14)
    mock_finnhub.return_value = [
        {
            "ticker": "NVDA",
            "company_name": "NVIDIA Corporation",
            "event_type": "Earnings Call / Results",
            "source_type": "SOURCED",
            "event_date": "2026-11-17",
            "display_date": "Nov 17, 2026",
            "headline": "NVIDIA Corporation Q3 2027 Earnings Release (After Market Close)",
            "details": "Consensus EPS Est: $2.47 | Consensus Rev Est: $108.13B",
            "source_url": "https://finnhub.io/quote/NVDA",
        }
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        init_db(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            INSERT INTO news_items (
                item_uid, ticker, company_name, source, source_label, source_type,
                headline, summary, url, published_date, form_or_type
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "uid_test_10q",
                "AAPL",
                "Apple Inc.",
                "sec_edgar",
                "SEC EDGAR",
                "regulatory_filing",
                "Apple Inc. Files Quarterly Financial Report (10-Q)",
                "Official SEC submission (10-Q). Accession: 0000320193-26-000050 | Report Period: 2026-06-30",
                "https://sec.gov/doc",
                "2026-08-01",
                "10-Q",
            ),
        )
        conn.commit()
        conn.close()

        watchlist = [
            {"symbol": "NVDA", "name": "NVIDIA Corporation"},
            {"symbol": "AAPL", "name": "Apple Inc."},
        ]

        events = build_forthcoming_calendar(
            watchlist=watchlist,
            db_path=db_path,
            api_key="mock_key",
        )

        assert len(events) >= 2
        tickers = [e["ticker"] for e in events]
        assert "NVDA" in tickers
        assert "AAPL" in tickers

        # Verify persisted in SQLite
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM calendar_events ORDER BY event_date ASC")
        rows = cur.fetchall()
        assert len(rows) == len(events)
        conn.close()
