"""Unit tests for Lightweight Quick-Lookup Feature (/functions/api/lookup.js & Search Integration)."""

import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import MagicMock, patch

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.lookup import (
    fetch_ticker_quick_lookup,
    format_time_ago,
)
from pipeline.render import render_dashboard


class TestQuickLookupFeature(unittest.TestCase):

    def setUp(self):
        self.project_root = Path(__file__).resolve().parent.parent

    def test_cloudflare_pages_function_exists_and_valid(self):
        """Verify functions/api/lookup.js exists with correct Cloudflare Pages structure."""
        fn_path = self.project_root / "functions" / "api" / "lookup.js"
        self.assertTrue(fn_path.exists(), "functions/api/lookup.js must exist")

        with open(fn_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check export handlers
        self.assertIn("export async function onRequestGet", content)
        self.assertIn("export async function onRequest", content)
        self.assertIn("FINNHUB_API_KEY", content)
        self.assertIn("https://finnhub.io/api/v1/quote", content)
        self.assertIn("https://finnhub.io/api/v1/company-news", content)
        self.assertIn("Access-Control-Allow-Origin", content)

    def test_format_time_ago(self):
        """Verify human-readable relative time formatting."""
        now = 1726430400
        with patch("pipeline.lookup.datetime") as mock_dt:
            mock_dt.utcnow.return_value.timestamp.return_value = now
            self.assertEqual(format_time_ago(now - 30), "Just now")
            self.assertEqual(format_time_ago(now - 300), "5m ago")
            self.assertEqual(format_time_ago(now - 7200), "2h ago")
            self.assertEqual(format_time_ago(now - 172800), "2d ago")
            self.assertEqual(format_time_ago(None), "")

    def test_fetch_ticker_quick_lookup_missing_ticker(self):
        """Verify error when ticker is empty or whitespace."""
        res = fetch_ticker_quick_lookup("")
        self.assertFalse(res["found"])
        self.assertIn("Missing ticker parameter", res.get("error", ""))

    def test_fetch_ticker_quick_lookup_missing_api_key(self):
        """Verify error when FINNHUB_API_KEY is unset."""
        with patch.dict(os.environ, {}, clear=True):
            res = fetch_ticker_quick_lookup("TSM", api_key="")
            self.assertFalse(res["found"])
            self.assertIn("FINNHUB_API_KEY", res.get("error", ""))

    def test_fetch_ticker_quick_lookup_success(self):
        """Verify successful Finnhub quote & news parsing and formatting."""
        mock_quote = {
            "c": 172.50,
            "d": 3.20,
            "dp": 1.89,
            "h": 174.10,
            "l": 170.80,
            "o": 171.00,
            "pc": 169.30,
            "t": 1726430400,
        }
        mock_news = [
            {
                "headline": "TSMC surges on record AI wafer demand and 2nm node progress",
                "url": "https://reuters.com/tsmc-record-demand",
                "source": "Reuters",
                "datetime": 1726425600,
                "summary": "Taiwan Semiconductor reports strong wafer demand from top hyperscalers.",
            },
            {
                "headline": "Semiconductor equipment bookings reach new high across Asia-Pacific",
                "url": "https://bloomberg.com/semi-bookings",
                "source": "Bloomberg",
                "datetime": 1726410000,
                "summary": "Foundry capex remains robust as AI accelerator production expands.",
            },
        ]

        def fake_urlopen(req, timeout=8):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            mock_resp = MagicMock()
            if "quote" in url:
                mock_resp.read.return_value = json.dumps(mock_quote).encode("utf-8")
            elif "company-news" in url:
                mock_resp.read.return_value = json.dumps(mock_news).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = fetch_ticker_quick_lookup("TSM", api_key="fake_token")

        self.assertTrue(res["found"])
        self.assertEqual(res["symbol"], "TSM")
        self.assertIsNotNone(res["price"])
        self.assertEqual(res["price"]["current"], 172.50)
        self.assertEqual(res["price"]["change"], 3.20)
        self.assertEqual(res["price"]["change_pct"], 1.89)
        self.assertEqual(res["price"]["high"], 174.10)
        self.assertEqual(res["price"]["low"], 170.80)

        # Check headlines
        self.assertEqual(len(res["headlines"]), 2)
        self.assertIn("TSMC surges", res["headlines"][0]["headline"])
        self.assertEqual(res["headlines"][0]["source"], "Reuters")
        self.assertIn("https://reuters.com", res["headlines"][0]["url"])

    def test_fetch_ticker_quick_lookup_not_found(self):
        """Verify handling when Finnhub returns empty/zero data for nonexistent ticker."""
        mock_empty_quote = {"c": 0, "d": 0, "dp": 0, "h": 0, "l": 0, "o": 0, "pc": 0, "t": 0}
        mock_empty_news = []

        def fake_urlopen(req, timeout=8):
            mock_resp = MagicMock()
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if "quote" in url:
                mock_resp.read.return_value = json.dumps(mock_empty_quote).encode("utf-8")
            else:
                mock_resp.read.return_value = json.dumps(mock_empty_news).encode("utf-8")
            mock_resp.__enter__.return_value = mock_resp
            return mock_resp

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            res = fetch_ticker_quick_lookup("NONEXISTENTTICKER99", api_key="fake_token")

        self.assertFalse(res["found"])
        self.assertIn("No quote or news found", res.get("message", ""))

    def test_rendered_index_contains_quick_lookup_markup(self):
        """Verify site/index.html includes Quick Lookup CSS styles and JS trigger functions."""
        out_index = self.project_root / "site" / "index.html"
        render_dashboard(output_path=str(out_index), performance_data={})

        with open(out_index, "r", encoding="utf-8") as f:
            content = f.read()

        # Check CSS classes
        self.assertIn("quick-lookup-card", content)
        self.assertIn("quick-lookup-badge", content)
        self.assertIn("quick-lookup-price-strip", content)
        self.assertIn("quick-lookup-headlines-list", content)

        # Check JavaScript integration
        self.assertIn("triggerLiveQuickLookup", content)
        self.assertIn("/api/lookup?ticker=", content)
        self.assertIn("isOutsideWatchlist", content)


if __name__ == "__main__":
    unittest.main()
