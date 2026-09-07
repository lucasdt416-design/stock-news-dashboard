"""Unit tests for the Company IR / Newsroom RSS Feed Collector."""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch
import urllib.error

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collectors.company_ir import collect_company_ir, fetch_ir_feed


class TestCompanyIRCollector(unittest.TestCase):

    @patch("collectors.company_ir.urllib.request.urlopen")
    def test_fetch_ir_feed_rss_success(self, mock_urlopen):
        sample_rss = b"""<?xml version="1.0" encoding="UTF-8"?>
        <rss version="2.0">
            <channel>
                <title>NVIDIA Newsroom</title>
                <link>https://nvidianews.nvidia.com</link>
                <description>NVIDIA Corporate News</description>
                <item>
                    <title>NVIDIA Announces Next-Generation Rubin AI Architecture</title>
                    <link>https://nvidianews.nvidia.com/news/rubin-architecture-launch</link>
                    <guid>https://nvidianews.nvidia.com/news/rubin-architecture-launch</guid>
                    <pubDate>Mon, 01 Sep 2026 14:00:00 GMT</pubDate>
                    <description><![CDATA[<p>NVIDIA founder and CEO announced the new Rubin architecture delivering 4x efficiency gains.</p>]]></description>
                </item>
            </channel>
        </rss>"""

        mock_resp = MagicMock()
        mock_resp.read.return_value = sample_rss
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        items = fetch_ir_feed(
            feed_url="https://nvidianews.nvidia.com/releases.xml",
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            max_items=10,
        )

        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["ticker"], "NVDA")
        self.assertEqual(item["company_name"], "NVIDIA Corporation")
        self.assertEqual(item["title"], "NVIDIA Announces Next-Generation Rubin AI Architecture")
        self.assertEqual(item["link"], "https://nvidianews.nvidia.com/news/rubin-architecture-launch")
        self.assertEqual(item["source"], "company_ir")
        self.assertEqual(item["source_type"], "company_announcement")
        self.assertEqual(item["form_or_type"], "PRESS_RELEASE")
        self.assertIn("Rubin architecture", item["summary"])
        self.assertNotIn("<p>", item["summary"])
        self.assertNotIn("</p>", item["summary"])
        self.assertTrue(item["published_date"].startswith("2026-09-01") or "2026" in item["published_date"])

    def test_fetch_ir_feed_empty_url(self):
        items = fetch_ir_feed(
            feed_url="",
            ticker="NVDA",
            company_name="NVIDIA Corporation",
        )
        self.assertEqual(items, [])

    @patch("collectors.company_ir.urllib.request.urlopen")
    def test_fetch_ir_feed_http_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            url="https://example.com/feed.xml",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=None,
        )

        items = fetch_ir_feed(
            feed_url="https://example.com/feed.xml",
            ticker="AAPL",
            company_name="Apple Inc.",
        )
        self.assertEqual(items, [])

    @patch("collectors.company_ir.urllib.request.urlopen")
    def test_fetch_ir_feed_url_error(self, mock_urlopen):
        mock_urlopen.side_effect = urllib.error.URLError("Connection refused")

        items = fetch_ir_feed(
            feed_url="https://example.com/feed.xml",
            ticker="AAPL",
            company_name="Apple Inc.",
        )
        self.assertEqual(items, [])

    @patch("collectors.company_ir.fetch_ir_feed")
    def test_collect_company_ir_watchlist(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "title": "Quarterly Earnings PR",
                "link": "https://example.com/pr1",
                "guid": "guid-1",
                "published_date": "2026-08-30",
                "published_time": "2026-08-30T10:00:00Z",
                "summary": "Record revenue report.",
                "source": "company_ir",
                "source_type": "company_announcement",
                "form_or_type": "PRESS_RELEASE",
            }
        ]

        watchlist = [
            {
                "symbol": "NVDA",
                "name": "NVIDIA Corporation",
                "ir_feed_url": "https://nvidianews.nvidia.com/releases.xml",
            },
            {
                "symbol": "NONEWS",
                "name": "No News Corp",
                "ir_feed_url": None,  # Should be skipped
            },
        ]

        results = collect_company_ir(watchlist=watchlist, delay_seconds=0.0)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["ticker"], "NVDA")
        mock_fetch.assert_called_once_with(
            "https://nvidianews.nvidia.com/releases.xml",
            ticker="NVDA",
            company_name="NVIDIA Corporation",
            max_items=30,
        )


if __name__ == "__main__":
    unittest.main()
