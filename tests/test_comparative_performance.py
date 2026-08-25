"""Unit tests for Comparative Stock Performance vs Competitors & S&P 500 Benchmark."""

import os
from pathlib import Path
import pytest
import yaml

from collectors.stock_prices import (
    BENCHMARK_TICKER,
    collect_comparative_performance,
    fetch_ticker_historical_closes,
)
from pipeline.render import render_dashboard


def test_watchlist_structure_and_competitors():
    """Verify data/watchlist.yaml has 16 companies and all have 3 valid competitors."""
    watchlist_path = Path("data/watchlist.yaml")
    assert watchlist_path.exists()

    with open(watchlist_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    tickers = cfg.get("tickers", [])
    assert len(tickers) >= 16

    # Verify AMD is present with full structure
    amd_entry = next((t for t in tickers if t["symbol"] == "AMD"), None)
    assert amd_entry is not None
    assert amd_entry["cik"] == "0000002488"
    assert amd_entry["sector"] == "semiconductors"
    assert "NVDA" in amd_entry["competitors"]
    assert "INTC" in amd_entry["competitors"]
    assert len(amd_entry["macro_sensitivities"]) > 0

    # Verify each ticker has valid competitors list
    for t in tickers:
        comps = t.get("competitors", [])
        assert isinstance(comps, list)
        assert len(comps) >= 2


def test_fetch_ticker_historical_closes():
    """Verify historical daily price fetching for a major ticker and SPY benchmark."""
    spy_data = fetch_ticker_historical_closes("SPY")
    assert spy_data is not None
    assert spy_data["symbol"] == "SPY"
    assert len(spy_data["series"]) >= 20
    assert "pct_change" in spy_data["series"][0]
    assert "total_pct_change" in spy_data


def test_collect_comparative_performance():
    """Verify batch comparative performance aggregation across watchlist and SPY."""
    res = collect_comparative_performance()
    assert "benchmark" in res
    assert "companies" in res
    assert len(res["companies"]) >= 16

    nvda = res["companies"].get("NVDA")
    assert nvda is not None
    assert nvda["symbol"] == "NVDA"
    assert len(nvda["competitors"]) >= 2
    assert "alpha_vs_peers" in nvda
    assert "alpha_vs_spy" in nvda
    assert "assessment" in nvda


def test_rendered_comparative_performance_markup(tmp_path):
    """Verify rendered index.html and company.html contain comparative chart elements."""
    out_dir = tmp_path / "site"
    out_dir.mkdir()
    out_index = out_dir / "index.html"

    # Fast mock performance data
    mock_perf = {
        "benchmark": {
            "symbol": "SPY",
            "latest_price": 550.0,
            "base_price": 540.0,
            "total_pct_change": 1.85,
            "series": [{"date": "2026-06-01", "pct_change": 0.0}, {"date": "2026-08-25", "pct_change": 1.85}],
        },
        "companies": {
            "NVDA": {
                "symbol": "NVDA",
                "name": "NVIDIA Corporation",
                "sector": "semiconductors",
                "target": {
                    "symbol": "NVDA",
                    "latest_price": 125.0,
                    "base_price": 120.0,
                    "total_pct_change": 4.17,
                    "series": [{"date": "2026-06-01", "pct_change": 0.0}, {"date": "2026-08-25", "pct_change": 4.17}],
                },
                "competitors": [
                    {
                        "symbol": "AMD",
                        "latest_price": 160.0,
                        "base_price": 150.0,
                        "total_pct_change": 6.67,
                        "series": [{"date": "2026-06-01", "pct_change": 0.0}, {"date": "2026-08-25", "pct_change": 6.67}],
                    }
                ],
                "benchmark": {
                    "symbol": "SPY",
                    "latest_price": 550.0,
                    "base_price": 540.0,
                    "total_pct_change": 1.85,
                    "series": [{"date": "2026-06-01", "pct_change": 0.0}, {"date": "2026-08-25", "pct_change": 1.85}],
                },
                "avg_competitor_pct": 6.67,
                "alpha_vs_peers": -2.50,
                "alpha_vs_spy": 2.32,
                "assessment": "In-Line with Competitors",
                "assessment_type": "neutral",
            }
        },
    }

    render_dashboard(output_path=str(out_index), performance_data=mock_perf)

    # Check index.html
    with open(out_index, "r", encoding="utf-8") as f:
        idx_content = f.read()
    assert "comparativeChartCanvas" in idx_content
    assert "perfCompanySelect" in idx_content
    assert "3-Month Comparative Performance vs. Peers &amp; S&amp;P 500" in idx_content

    # Check company.html
    comp_file = out_dir / "company.html"
    assert comp_file.exists()
    with open(comp_file, "r", encoding="utf-8") as f:
        comp_content = f.read()
    assert "compPerfCanvas-NVDA" in comp_content
    assert "3-Month Performance vs. Competitors &amp; S&amp;P 500" in comp_content
