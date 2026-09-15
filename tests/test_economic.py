"""Tests for Macroeconomic Intelligence Engine (Category #15).

Verifies:
1. 5 FRED Indicators (Fed Funds, 10Y Treasury, CPI YoY, WTI Crude Oil, Unemployment).
2. 12-24 month historical data series structure for sparklines.
3. AI-driven one-line executive synthesis generation and fallback logic.
4. Upcoming macroeconomic events schedule (FOMC, EIA, BLS Jobs, BLS CPI).
5. SQLite schema migration and persistence for history_json and ai_synthesis.
6. Full page rendering of site/economic.html with sparklines, events strip, and 5 indicator cards.
"""

import json
import os
import sqlite3
import pytest
from pipeline.economic import (
    FALLBACK_INDICATORS,
    collect_economic_indicators,
    generate_economic_synthesis,
    get_upcoming_economic_events,
    init_economic_schema,
)
from pipeline.persist import get_economic_indicators
from pipeline.render import render_dashboard


def test_fallback_indicators_structure():
    """Verify all 5 required macro indicators exist with complete 12-24 month histories."""
    expected_keys = {"interest_rates", "treasury_10y", "inflation", "crude_oil", "unemployment"}
    assert set(FALLBACK_INDICATORS.keys()) == expected_keys

    for key, ind in FALLBACK_INDICATORS.items():
        assert ind["indicator_id"] == key
        assert ind["series_id"]
        assert ind["name"]
        assert ind["category"]
        assert isinstance(ind["current_value"], (int, float))
        assert ind["formatted_value"]
        assert ind["unit"]
        assert ind["change_direction"] in ("up", "down", "flat")
        assert "history" in ind
        assert len(ind["history"]) >= 12
        for pt in ind["history"]:
            assert "date" in pt
            assert "value" in pt
            assert isinstance(pt["value"], (int, float))


def test_upcoming_economic_events():
    """Verify upcoming economic events return schedule with required metadata."""
    events = get_upcoming_economic_events()
    assert len(events) >= 4
    event_ids = [e["event_id"] for e in events]
    assert "fomc_decision" in event_ids
    assert "eia_petroleum" in event_ids
    assert "bls_jobs" in event_ids
    assert "bls_cpi" in event_ids

    for ev in events:
        assert ev["title"]
        assert ev["date"]
        assert ev["display_date"]
        assert ev["relative_badge"]
        assert ev["authority"]
        assert ev["consensus"]
        assert ev["impact_area"]


def test_generate_economic_synthesis_heuristics():
    """Verify deterministic fallback synthesis creates sharp, ticker-specific takeaways."""
    # 10Y Treasury
    synth_10y = generate_economic_synthesis(
        indicator_id="treasury_10y",
        name="10-Year Treasury Yield",
        formatted_val="4.28%",
        change_dir="up",
        change_val=0.05,
        relevant_tickers=["JPM", "GS", "BAC"],
    )
    assert "JPM, GS, BAC" in synth_10y or "JPM" in synth_10y
    assert "4.28%" in synth_10y

    # Crude Oil
    synth_oil = generate_economic_synthesis(
        indicator_id="crude_oil",
        name="WTI Crude Oil",
        formatted_val="$76.50 / bbl",
        change_dir="down",
        change_val=-1.20,
        relevant_tickers=["XOM", "CVX", "BA"],
    )
    assert "$76.50 / bbl" in synth_oil
    assert "XOM, CVX, BA" in synth_oil or "XOM" in synth_oil

    # Interest Rates
    synth_rates = generate_economic_synthesis(
        indicator_id="interest_rates",
        name="Fed Funds",
        formatted_val="3.75%",
        change_dir="flat",
        change_val=0.0,
        relevant_tickers=["JPM", "BAC"],
    )
    assert "3.75%" in synth_rates


def test_economic_db_schema_and_persistence(tmp_path):
    """Test SQLite initialization, collection, and retrieval with history_json and ai_synthesis."""
    db_file = str(tmp_path / "test_macro.db")

    # Collect indicators
    indicators = collect_economic_indicators(api_key=None, db_path=db_file)
    assert len(indicators) == 5

    # Retrieve via persist module
    fetched = get_economic_indicators(db_path=db_file)
    assert len(fetched) == 5

    indicator_ids = [d["indicator_id"] for d in fetched]
    assert indicator_ids == ["interest_rates", "treasury_10y", "inflation", "crude_oil", "unemployment"]

    for d in fetched:
        assert len(d["history"]) >= 12
        assert d["ai_synthesis"]
        assert len(d["ai_synthesis"]) > 10
        assert "tickers_list" in d
        assert len(d["tickers_list"]) > 0


def test_render_economic_page(tmp_path):
    """Test end-to-end rendering of site/economic.html containing all 5 cards, sparklines, events strip, and synthesis."""
    db_file = str(tmp_path / "render_macro.db")
    site_dir = str(tmp_path / "site")
    os.makedirs(site_dir, exist_ok=True)

    # Auto-seed db
    collect_economic_indicators(api_key=None, db_path=db_file)

    render_dashboard(output_path=os.path.join(site_dir, "index.html"), db_path=db_file)

    econ_html_path = os.path.join(site_dir, "economic.html")
    assert os.path.exists(econ_html_path)

    with open(econ_html_path, "r", encoding="utf-8") as f:
        content = f.read()

    # Check for upcoming events strip
    assert "Upcoming Macroeconomic Releases" in content
    assert "FOMC Interest Rate Decision" in content
    assert "EIA Weekly Petroleum Status Report" in content
    assert "Employment Situation (Nonfarm Payrolls)" in content
    assert "Consumer Price Index (CPI Report)" in content

    # Check for all 5 indicators
    assert "Federal Funds Target Rate" in content
    assert "10-Year Treasury Benchmark Yield" in content
    assert "Consumer Price Index (CPI YoY)" in content
    assert "WTI Crude Oil Spot Price" in content
    assert "Civilian Unemployment Rate" in content

    # Check for sparklines & AI synthesis
    assert "sparkline-wrapper" in content
    assert "renderEconSparklines" in content
    assert "AI Macro Takeaway" in content

    # Check for sensitive holdings mapped
    assert "JPM" in content
    assert "XOM" in content
    assert "CVX" in content
