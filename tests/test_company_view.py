import os
import sys
import tempfile
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.calendar import build_forthcoming_calendar, init_calendar_schema
from pipeline.db import get_db_connection, init_db
from pipeline.persist import save_news_items
from pipeline.render import render_dashboard


class TestCompanyViewAndRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_dashboard.db")
        cls.site_dir = os.path.join(cls.temp_dir.name, "site")
        os.makedirs(cls.site_dir, exist_ok=True)
        init_db(cls.db_path)

        sample_items = [
            {
                "item_uid": "test-nvda-8k-001",
                "source": "sec_edgar",
                "ticker": "NVDA",
                "company_name": "NVIDIA Corporation",
                "form_or_type": "8-K",
                "form": "8-K",
                "headline": "NVIDIA Files Current Report",
                "summary": "Sample filing",
                "url": "https://sec.gov/sample-nvda",
                "published_date": "2026-09-15",
                "score": 8.5,
                "category": "Company Announcement",
            },
            {
                "item_uid": "test-ba-news-002",
                "source": "news_media",
                "ticker": "BA",
                "company_name": "The Boeing Company",
                "form_or_type": "NEWS",
                "headline": "Boeing Secures Commercial Airline Delivery Order",
                "summary": "Sample aerospace report",
                "url": "https://reuters.com/sample-boeing",
                "published_date": "2026-09-14",
                "score": 7.2,
                "category": "Product & Commercial Announcements",
            },
        ]
        save_news_items(sample_items, db_path=cls.db_path)

        with get_db_connection(cls.db_path) as conn:
            init_calendar_schema(conn)
            conn.execute(
                """
                INSERT INTO calendar_events (
                    ticker, company_name, event_type, source_type,
                    event_date, display_date, relative_badge, headline,
                    details, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "NVDA",
                    "NVIDIA Corporation",
                    "Earnings Call",
                    "SOURCED",
                    "2026-11-18",
                    "Nov 18, 2026",
                    "in 63 days",
                    "Q3 FY2027 Financial Results Conference Call",
                    "Live webcast and earnings release.",
                    "https://nvidianews.nvidia.com",
                    "2026-09-15 00:00:00Z",
                ),
            )
            conn.commit()

        # Render static site without slow external network dependencies
        render_dashboard(
            output_path=os.path.join(cls.site_dir, "index.html"),
            db_path=cls.db_path,
            performance_data={},
        )

    @classmethod
    def tearDownClass(cls):
        cls.temp_dir.cleanup()

    def test_company_html_exists(self):
        company_path = os.path.join(self.site_dir, "company.html")
        self.assertTrue(os.path.exists(company_path), "company.html must be generated")

        with open(company_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify company switcher strip
        self.assertIn("company-strip", content)
        self.assertIn("data-ticker=\"BA\"", content)
        self.assertIn("data-ticker=\"NVDA\"", content)
        self.assertIn("data-ticker=\"AAPL\"", content)

        # Verify sections for Boeing (BA)
        self.assertIn("id=\"profile-BA\"", content)
        self.assertIn("The Boeing Company", content)
        self.assertIn("Corporate Ecosystem", content)
        self.assertIn("Macroeconomic Sensitivities", content)
        self.assertIn("Forthcoming Calendar", content)
        self.assertIn("Intelligence Feed", content)

        # Verify human-readable Newsroom links
        self.assertIn("https://nvidianews.nvidia.com", content)
        self.assertIn("Newsroom ↗", content)

        # Verify company card layout structure & classes
        self.assertIn("company-browser-grid", content)
        self.assertIn("company-browser-card-left", content)
        self.assertIn("company-browser-card-info", content)
        self.assertIn("company-browser-card-name", content)
        self.assertIn("company-browser-card-sec", content)
        self.assertIn("company-browser-card-stats", content)
        self.assertIn("company-browser-card-alpha", content)
        self.assertIn("company-browser-card-stories", content)

        # Verify longest watchlist company names are present
        self.assertIn("The Goldman Sachs Group, Inc.", content)
        self.assertIn("UnitedHealth Group Incorporated", content)
        self.assertIn("Costco Wholesale Corporation", content)
        self.assertIn("The Procter &amp; Gamble Company", content)

    def test_ticker_links_across_pages(self):
        index_path = os.path.join(self.site_dir, "index.html")
        news_path = os.path.join(self.site_dir, "news.html")
        calendar_path = os.path.join(self.site_dir, "calendar.html")
        economic_path = os.path.join(self.site_dir, "economic.html")

        with open(index_path, "r", encoding="utf-8") as f:
            index_html = f.read()
        self.assertIn("company.html?ticker=", index_html)

        with open(news_path, "r", encoding="utf-8") as f:
            news_html = f.read()
        self.assertIn("company.html?ticker=", news_html)
        self.assertIn("data-val=\"news_media\"", news_html)
        self.assertIn("News Media", news_html)

        with open(calendar_path, "r", encoding="utf-8") as f:
            cal_html = f.read()
        self.assertIn("company.html?ticker=", cal_html)

        with open(economic_path, "r", encoding="utf-8") as f:
            econ_html = f.read()
        self.assertIn("company.html?ticker=", econ_html)

    def test_recently_viewed_section(self):
        index_path = os.path.join(self.site_dir, "index.html")
        company_path = os.path.join(self.site_dir, "company.html")

        with open(index_path, "r", encoding="utf-8") as f:
            index_html = f.read()
        self.assertIn("recentlyViewedSection", index_html)
        self.assertIn("recentlyViewedGrid", index_html)
        self.assertIn("Recently Viewed Companies", index_html)
        self.assertIn("renderRecentlyViewed", index_html)
        self.assertIn("clearRecentlyViewed", index_html)

        with open(company_path, "r", encoding="utf-8") as f:
            company_html = f.read()
        self.assertIn("trackRecentlyViewedCompany", company_html)
        self.assertIn("stockpulse_recently_viewed", company_html)

    def test_analytics_page_exists_and_renders(self):
        analytics_path = os.path.join(self.site_dir, "analytics.html")
        self.assertTrue(os.path.exists(analytics_path), "analytics.html must be generated")

        with open(analytics_path, "r", encoding="utf-8") as f:
            analytics_html = f.read()

        # Check charts, comparative perf, and telemetry
        self.assertIn("timelineChart", analytics_html)
        self.assertIn("categoryChart", analytics_html)
        self.assertIn("comparativeChartCanvas", analytics_html)
        self.assertIn("perfCompanySelect", analytics_html)
        self.assertIn("Pipeline Health &amp; Safeguards", analytics_html)
        self.assertIn("SEC EDGAR Filings", analytics_html)


if __name__ == "__main__":
    unittest.main()
