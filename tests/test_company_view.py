import os
import unittest
from pipeline.render import render_dashboard


class TestCompanyViewAndRender(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Render static site to test directory or verify existing
        render_dashboard()
        cls.site_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "site")

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


if __name__ == "__main__":
    unittest.main()
