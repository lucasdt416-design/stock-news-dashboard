"""Unit tests for database retention pruning and 1,000-item safety cap."""

from datetime import datetime, timedelta, timezone
import os
import sys
import tempfile
import unittest

# Ensure project root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pipeline.db import get_db_connection, init_db
from pipeline.health import record_pipeline_run_health
from pipeline.persist import prune_news_items, save_news_items


class TestDatabasePruning(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_dashboard.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_prune_items_older_than_90_days(self):
        """Verify items older than 90 days are deleted while newer items remain."""
        now = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

        # 2 items older than 90 days (100d, 120d ago)
        old_items = [
            {
                "item_uid": "old-1",
                "ticker": "NVDA",
                "headline": "Old 100-day filing",
                "url": "https://example.com/old1",
                "published_date": (now - timedelta(days=100)).strftime("%Y-%m-%d"),
                "source": "sec_edgar",
                "score": 5.0,
            },
            {
                "item_uid": "old-2",
                "ticker": "AAPL",
                "headline": "Old 120-day news",
                "url": "https://example.com/old2",
                "published_date": (now - timedelta(days=120)).strftime("%Y-%m-%d"),
                "source": "news_media",
                "score": 6.0,
            },
        ]

        # 3 items within 90 days (10d, 30d, 80d ago)
        new_items = [
            {
                "item_uid": "new-1",
                "ticker": "NVDA",
                "headline": "Recent 10-day release",
                "url": "https://example.com/new1",
                "published_date": (now - timedelta(days=10)).strftime("%Y-%m-%d"),
                "source": "company_ir",
                "score": 8.0,
            },
            {
                "item_uid": "new-2",
                "ticker": "MSFT",
                "headline": "Recent 30-day filing",
                "url": "https://example.com/new2",
                "published_date": (now - timedelta(days=30)).strftime("%Y-%m-%d"),
                "source": "sec_edgar",
                "score": 7.0,
            },
            {
                "item_uid": "new-3",
                "ticker": "AMD",
                "headline": "Recent 80-day article",
                "url": "https://example.com/new3",
                "published_date": (now - timedelta(days=80)).strftime("%Y-%m-%d"),
                "source": "news_media",
                "score": 6.5,
            },
        ]

        save_news_items(old_items + new_items, db_path=self.db_path)

        stats = prune_news_items(
            max_age_days=90,
            max_total_items=1000,
            db_path=self.db_path,
            reference_date=now,
        )

        self.assertEqual(stats["initial_count"], 5)
        self.assertEqual(stats["deleted_by_age"], 2)
        self.assertEqual(stats["deleted_by_cap"], 0)
        self.assertEqual(stats["total_deleted"], 2)
        self.assertEqual(stats["remaining_count"], 3)

        # Verify remaining items in DB
        conn = get_db_connection(self.db_path)
        uids = [row["item_uid"] for row in conn.execute("SELECT item_uid FROM news_items").fetchall()]
        conn.close()

        self.assertIn("new-1", uids)
        self.assertIn("new-2", uids)
        self.assertIn("new-3", uids)
        self.assertNotIn("old-1", uids)
        self.assertNotIn("old-2", uids)

    def test_enforce_hard_safety_cap(self):
        """Verify hard cap deletes oldest items beyond the limit even if within 90 days."""
        now = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

        # Create 8 items, all within 90 days (days 1 to 8)
        items = []
        for i in range(1, 9):
            items.append({
                "item_uid": f"item-{i}",
                "ticker": "NVDA",
                "headline": f"Item {i} headline",
                "url": f"https://example.com/item-{i}",
                "published_date": (now - timedelta(days=i)).strftime("%Y-%m-%d"),
                "source": "sec_edgar",
                "score": 5.0,
            })

        save_news_items(items, db_path=self.db_path)

        # Cap at 4 items
        stats = prune_news_items(
            max_age_days=90,
            max_total_items=4,
            db_path=self.db_path,
            reference_date=now,
        )

        self.assertEqual(stats["initial_count"], 8)
        self.assertEqual(stats["deleted_by_age"], 0)
        self.assertEqual(stats["deleted_by_cap"], 4)
        self.assertEqual(stats["total_deleted"], 4)
        self.assertEqual(stats["remaining_count"], 4)

        # The 4 newest (days 1, 2, 3, 4) should remain
        conn = get_db_connection(self.db_path)
        uids = [row["item_uid"] for row in conn.execute("SELECT item_uid FROM news_items ORDER BY published_date DESC").fetchall()]
        conn.close()

        self.assertEqual(uids, ["item-1", "item-2", "item-3", "item-4"])

    def test_pipeline_runs_table_is_preserved(self):
        """Verify pipeline_runs health history is unaffected by news item pruning."""
        now = datetime(2026, 9, 6, 12, 0, 0, tzinfo=timezone.utc)

        # Insert some news items
        save_news_items([
            {
                "item_uid": "old-doc",
                "ticker": "NVDA",
                "headline": "150-day old filing",
                "url": "https://example.com/150",
                "published_date": (now - timedelta(days=150)).strftime("%Y-%m-%d"),
                "source": "sec_edgar",
            }
        ], db_path=self.db_path)

        # Insert 3 health run records
        for i in range(3):
            record_pipeline_run_health(
                collector_counts={"sec_edgar": 10, "company_ir": 5, "news_media": 5},
                total_raw=20,
                total_unique=18,
                high_impact_count=2,
                db_path=self.db_path,
            )

        # Prune news items
        stats = prune_news_items(
            max_age_days=90,
            max_total_items=1000,
            db_path=self.db_path,
            reference_date=now,
        )

        self.assertEqual(stats["deleted_by_age"], 1)
        self.assertEqual(stats["remaining_count"], 0)

        # Verify pipeline_runs still has all 3 records intact
        conn = get_db_connection(self.db_path)
        runs_count = conn.execute("SELECT count(*) FROM pipeline_runs").fetchone()[0]
        conn.close()

        self.assertEqual(runs_count, 3)

    def test_prune_empty_database(self):
        """Verify prune on empty database runs gracefully without errors."""
        stats = prune_news_items(
            max_age_days=90,
            max_total_items=1000,
            db_path=self.db_path,
        )
        self.assertEqual(stats["initial_count"], 0)
        self.assertEqual(stats["total_deleted"], 0)
        self.assertEqual(stats["remaining_count"], 0)


if __name__ == "__main__":
    unittest.main()
