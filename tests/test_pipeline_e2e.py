"""End-to-End Pipeline & Signature Regression Test Suite.

Validates that all 12 pipeline stages, collector entry points, and script runner
functions accept their expected keyword and positional arguments, ensuring that
any signature drift or parameter mismatch is detected before deployment.
"""

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import yaml

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from collectors.company_ir import collect_company_ir
from collectors.edgar import collect_edgar_filings, collect_sec_edgar
from collectors.finnhub_news import collect_finnhub_news
from collectors.stock_prices import collect_comparative_performance
from pipeline.calendar import build_forthcoming_calendar
from pipeline.crossref import apply_supply_chain_cross_references
from pipeline.db import init_db
from pipeline.dedupe import deduplicate_items
from pipeline.economic import collect_economic_indicators
from pipeline.health import record_pipeline_run_health
from pipeline.lookup import fetch_ticker_quick_lookup
from pipeline.normalize import normalize_items
from pipeline.persist import (
    get_news_stats,
    prune_news_items,
    rescore_database_items,
    save_news_items,
)
from pipeline.render import render_dashboard
from pipeline.score import score_items
from pipeline.summarize import summarize_items


class TestPipelineEndToEnd(unittest.TestCase):
    """Test full pipeline stages and signature compatibility."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.temp_dir.name)
        self.db_path = str(self.tmp_path / "test_pipeline.db")
        self.site_dir = self.tmp_path / "site"
        self.site_dir.mkdir(parents=True, exist_ok=True)
        self.index_html = str(self.site_dir / "index.html")

        self.watchlist_data = {
            "tickers": [
                {
                    "symbol": "NVDA",
                    "name": "NVIDIA Corporation",
                    "sector": "Technology",
                    "cik": "0001045810",
                    "key_customers": ["MSFT", "GOOGL", "AMZN", "META", "TSLA"],
                    "key_suppliers": ["TSM", "ASML"],
                    "competitors": ["AMD", "INTC"],
                    "macro_sensitivities": ["interest_rates", "treasury_10y"],
                },
                {
                    "symbol": "AMD",
                    "name": "Advanced Micro Devices",
                    "sector": "Technology",
                    "cik": "0000002488",
                    "key_customers": ["MSFT", "Sony"],
                    "key_suppliers": ["TSM"],
                    "competitors": ["NVDA", "INTC"],
                    "macro_sensitivities": ["interest_rates"],
                },
            ]
        }
        self.watchlist_file = str(self.tmp_path / "watchlist.yaml")
        with open(self.watchlist_file, "w", encoding="utf-8") as f:
            yaml.dump(self.watchlist_data, f)

        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_all_12_pipeline_stages_signatures_and_execution(self):
        """Execute all 12 pipeline stages sequentially using exact signatures used in run_local.py."""
        tickers = self.watchlist_data["tickers"]

        # 1. SEC EDGAR Collector (test alias and user_agent kwarg)
        edgar_items = collect_sec_edgar(
            watchlist=tickers,
            user_agent="StockNewsDashboard-Test/1.0",
            max_items_per_ticker=2,
            delay_seconds=0.0,
        )
        self.assertIsInstance(edgar_items, list)

        # 2. Company IR Collector
        ir_items = collect_company_ir(
            watchlist=tickers,
            max_items_per_ticker=2,
            delay_seconds=0.0,
        )
        self.assertIsInstance(ir_items, list)

        # 3. Finnhub News Collector
        finnhub_items = collect_finnhub_news(
            watchlist=tickers,
            days_back=7,
            max_items_per_ticker=2,
            delay_seconds=0.0,
            api_key="",
        )
        self.assertIsInstance(finnhub_items, list)

        # Create representative synthetic items across sources
        synthetic_raw = [
            {
                "source": "sec_edgar",
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "form": "8-K",
                "filing_date": "2026-09-15",
                "report_date": "2026-09-15",
                "acceptance_date_time": "2026-09-15 17:00:00",
                "accession_number": "0001045810-26-000001",
                "primary_doc_name": "nvda-8k.htm",
                "primary_doc_description": "Current Report Item 1.01",
                "url": "https://www.sec.gov/Archives/edgar/data/1045810/000104581026000001/nvda-8k.htm",
            },
            {
                "source": "company_ir",
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "headline": "NVIDIA and TSMC Expand Next-Gen Packaging Architecture",
                "url": "https://nvidianews.nvidia.com/releases/next-gen-packaging",
                "published_date": "2026-09-15",
                "content": "NVIDIA today announced expanded co-development with key partner TSM.",
            },
            {
                "source": "news_media",
                "ticker": "AMD",
                "company_name": "Advanced Micro Devices",
                "headline": "AMD Unveils New MI350 AI Accelerator Architecture",
                "url": "https://finance.yahoo.com/news/amd-mi350-launch",
                "published_date": "2026-09-14",
                "summary": "AMD targets increased cloud workload share.",
            },
        ]

        # 4. Stage 4: Normalize Records
        normalized = normalize_items(synthetic_raw)
        self.assertEqual(len(normalized), 3)

        # 5. Stage 5: Deduplicate Across Sources
        dedup_res = deduplicate_items(normalized, db_path=self.db_path)
        if isinstance(dedup_res, tuple):
            unique_items, dupes_removed = dedup_res
        else:
            unique_items = dedup_res
        self.assertEqual(len(unique_items), 3)

        # 6. Stage 6: Cross-Referencing (test with watchlist_path and with direct watchlist)
        crossref_items = apply_supply_chain_cross_references(
            unique_items,
            watchlist_path=self.watchlist_file,
        )
        self.assertEqual(len(crossref_items), 3)
        nvda_ir = next(it for it in crossref_items if it.get("source") == "company_ir")
        self.assertIn("TSM", nvda_ir.get("related_tickers", []))

        # 7. Stage 7: Scoring Engine
        scored_items = score_items(crossref_items, watchlist_path=self.watchlist_file)
        self.assertEqual(len(scored_items), 3)
        for it in scored_items:
            self.assertIn("score", it)
            self.assertIsInstance(it["score"], (int, float))

        # 8. Stage 7b: AI / Heuristic Summarization
        summarized_items = summarize_items(scored_items, watchlist_path=self.watchlist_file)
        self.assertEqual(len(summarized_items), 3)
        for it in summarized_items:
            self.assertTrue(it.get("llm_summary"))

        # 9. Stage 8: Persist to Database & Rescore
        saved_count, total_count = save_news_items(summarized_items, db_path=self.db_path)
        self.assertEqual(saved_count, 3)
        rescored = rescore_database_items(
            db_path=self.db_path,
            watchlist_path=self.watchlist_file,
        )
        self.assertEqual(rescored, 3)

        # 10. Database Pruning
        prune_stats = prune_news_items(
            max_age_days=90,
            max_items=1000,
            db_path=self.db_path,
        )
        self.assertEqual(prune_stats["remaining_count"], 3)

        # 11. Health Monitoring Safeguards
        health_report = record_pipeline_run_health(
            collector_counts={"sec_edgar": 1, "company_ir": 1, "news_media": 1},
            total_raw=3,
            total_unique=3,
            high_impact_count=1,
            db_path=self.db_path,
        )
        self.assertIn(health_report["status"].lower(), ("healthy", "warning", "critical"))

        # 12. Calendar & Economic Indicators
        cal_events = build_forthcoming_calendar(
            watchlist=tickers,
            db_path=self.db_path,
            api_key="",
        )
        self.assertIsInstance(cal_events, list)

        econ_indicators = collect_economic_indicators(
            watchlist=tickers,
            db_path=self.db_path,
        )
        self.assertEqual(len(econ_indicators), 5)

        # 13. Stock Performance Mock
        perf_data = {
            "benchmark": {"symbol": "SPY", "series": []},
            "companies": {
                "NVDA": {
                    "symbol": "NVDA",
                    "target": {"symbol": "NVDA", "series": []},
                    "competitors": [{"symbol": "AMD", "series": []}],
                }
            },
        }

        # 14. Render Static Pages
        output_file = render_dashboard(
            output_path=self.index_html,
            db_path=self.db_path,
            performance_data=perf_data,
        )
        self.assertTrue(os.path.exists(output_file))

        # Verify all 6 pages exist and are non-empty
        for page_name in ["index.html", "news.html", "calendar.html", "economic.html", "company.html", "analytics.html"]:
            page_path = self.site_dir / page_name
            self.assertTrue(page_path.exists(), f"{page_name} must be rendered")
            self.assertGreater(page_path.stat().st_size, 500, f"{page_name} must not be empty")

    def test_run_local_script_main_execution_mocked(self):
        """Verify scripts/run_local.py main() executes without crashing when collectors return data."""
        from scripts.run_local import main

        mock_filings = [
            {
                "source": "sec_edgar",
                "ticker": "NVDA",
                "company_name": "NVIDIA",
                "form": "8-K",
                "filing_date": "2026-09-15",
                "report_date": "2026-09-15",
                "acceptance_date_time": "2026-09-15 17:00:00",
                "accession_number": "0001045810-26-000001",
                "primary_doc_name": "nvda-8k.htm",
                "primary_doc_description": "Current Report",
                "url": "https://www.sec.gov/test",
            }
        ]

        with patch("scripts.run_local.collect_sec_edgar", return_value=mock_filings), \
             patch("scripts.run_local.collect_company_ir", return_value=[]), \
             patch("scripts.run_local.collect_finnhub_news", return_value=[]), \
             patch("scripts.run_local.collect_comparative_performance", return_value={"benchmark": {}, "companies": {}}), \
             patch("sys.argv", ["run_local.py", "--prune-only"]):
            # Should execute cleanly without raising any exceptions
            try:
                main()
            except SystemExit as e:
                self.assertEqual(e.code, 0)


if __name__ == "__main__":
    unittest.main()
