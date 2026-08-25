import os
import unittest
from unittest.mock import patch, MagicMock
from collectors.finnhub_news import fetch_company_news_finnhub, collect_finnhub_news
from pipeline.normalize import normalize_items
from pipeline.classify import classify_item
from pipeline.score import score_item


class TestFinnhubNewsCollector(unittest.TestCase):

    @patch("collectors.finnhub_news.urllib.request.urlopen")
    def test_fetch_company_news_finnhub_success(self, mock_urlopen):
        mock_response = MagicMock()
        mock_response.status = 200
        mock_response.read.return_value = b"""[
            {
                "category": "company",
                "datetime": 1740400000,
                "headline": "FAA grounds Boeing 737 MAX fleet following safety review and emergency inspection",
                "id": 10928374,
                "image": "https://example.com/boeing_plane.jpg",
                "related": "BA",
                "source": "Reuters",
                "summary": "Federal Aviation Administration announces immediate review of Boeing manufacturing lines.",
                "url": "https://www.reuters.com/business/aerospace-defense/boeing-safety-review"
            }
        ]"""
        mock_response.__enter__.return_value = mock_response
        mock_urlopen.return_value = mock_response

        items = fetch_company_news_finnhub(
            symbol="BA",
            from_date="2025-01-01",
            to_date="2025-01-15",
            api_key="fake_test_key"
        )
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["ticker"], "BA")
        self.assertEqual(item["source"], "news_media")
        self.assertEqual(item["source_label"], "News Media")
        self.assertEqual(item["publisher"], "Reuters")
        self.assertEqual(item["raw_id"], "10928374")
        self.assertIn("grounds Boeing 737", item["headline"])

    def test_collect_finnhub_news_without_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            items = collect_finnhub_news(watchlist=[{"symbol": "BA", "name": "The Boeing Company"}])
            self.assertEqual(items, [])

    @patch("collectors.finnhub_news.fetch_company_news_finnhub")
    def test_collect_finnhub_news_with_mock_data(self, mock_fetch):
        mock_fetch.return_value = [
            {
                "raw_id": "99901",
                "ticker": "BA",
                "source": "news_media",
                "source_label": "News Media",
                "source_type": "press",
                "publisher": "Bloomberg",
                "headline": "Boeing faces new supplier lawsuit over fuselage delivery delays",
                "summary": "Spirit AeroSystems litigation expands over contract breach.",
                "url": "https://bloomberg.com/news/boeing-lawsuit",
                "published_epoch": 1740410000,
                "category_raw": "company",
                "image_url": "https://example.com/img.jpg"
            }
        ]

        with patch.dict(os.environ, {"FINNHUB_API_KEY": "test_token"}):
            items = collect_finnhub_news(
                watchlist=[{"symbol": "BA", "name": "The Boeing Company"}],
                delay_seconds=0.0
            )
            self.assertGreaterEqual(len(items), 1)
            self.assertEqual(items[0]["publisher"], "Bloomberg")

    def test_news_media_normalization(self):
        raw_news = [{
            "raw_id": "12345",
            "ticker": "BA",
            "source": "news_media",
            "source_label": "News Media",
            "source_type": "press",
            "publisher": "Reuters",
            "headline": "Boeing 737 MAX emergency grounding ordered after flight incident",
            "summary": "Aviation authorities issue directive affecting worldwide operations.",
            "url": "https://reuters.com/boeing-incident",
            "published_date": "2025-02-24",
            "published_time": "2025-02-24T12:00:00Z",
            "category_raw": "company"
        }]

        normalized = normalize_items(raw_news)
        self.assertEqual(len(normalized), 1)
        item = normalized[0]
        self.assertEqual(item["source"], "news_media")
        self.assertEqual(item["source_label"], "News Media")
        self.assertEqual(item["publisher"], "Reuters")
        self.assertTrue(len(item["item_uid"]) >= 12)
        self.assertTrue(item["published_date"].startswith("2025-") or item["published_date"].startswith("2026-"))

    def test_journalistic_classification_rules(self):
        item_crash = {
            "ticker": "BA",
            "headline": "FAA orders inspection after Boeing plane crash and cabin emergency",
            "summary": "Aircraft safety investigation underway."
        }
        self.assertEqual(classify_item(item_crash), "Regulation & Policy / Litigation")

        item_recall = {
            "ticker": "TSLA",
            "headline": "Tesla issues voluntary product recall for power steering software defect",
            "summary": "NHTSA notices posted for over 200,000 electric vehicles."
        }
        self.assertEqual(classify_item(item_recall), "Regulation & Policy / Litigation")

        item_lawsuit = {
            "ticker": "AAPL",
            "headline": "DOJ files antitrust lawsuit targeting Apple App Store monopolistic practices",
            "summary": "Federal complaint filed in district court."
        }
        self.assertEqual(classify_item(item_lawsuit), "Regulation & Policy / Litigation")

    def test_news_media_scoring_breakdown(self):
        item = {
            "ticker": "BA",
            "source": "news_media",
            "category": "Regulation & Policy / Litigation",
            "form_or_type": "News Media",
            "headline": "Boeing faces massive FAA grounding and NTSB criminal investigation into safety culture",
            "summary": "Federal regulators and prosecutors open inquiry.",
            "cross_references_list": [{"related_ticker": "BA", "relation_type": "Supplier"}]
        }

        scored = score_item(item)
        score = scored["score"]
        breakdown = scored["score_breakdown"]
        self.assertGreaterEqual(score, 7.0)
        self.assertIn("Source: +1 (News Media / Press)", breakdown)
        self.assertIn("Base: 7 (Regulation & Policy / Litigation)", breakdown)


if __name__ == "__main__":
    unittest.main()
