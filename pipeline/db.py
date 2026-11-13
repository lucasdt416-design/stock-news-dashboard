"""Database connection and schema management for stock news dashboard."""

import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "data", "dashboard.db"
)


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a connection to the SQLite database with Row factory enabled."""
    target_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database schema and perform backwards-compatible migrations."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_uid TEXT UNIQUE NOT NULL,
                ticker TEXT NOT NULL,
                company_name TEXT,
                source TEXT NOT NULL,
                source_label TEXT NOT NULL,
                source_type TEXT NOT NULL,
                headline TEXT NOT NULL,
                summary TEXT,
                url TEXT NOT NULL,
                published_date TEXT NOT NULL,
                published_time TEXT,
                form_or_type TEXT,
                raw_id TEXT,
                category TEXT,
                score REAL NOT NULL DEFAULT 0.0,
                score_breakdown TEXT,
                llm_summary TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Migration helper for existing databases
        cursor = conn.execute("PRAGMA table_info(news_items)")
        columns = [row["name"] for row in cursor.fetchall()]

        if "category" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN category TEXT")
        if "score" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN score REAL NOT NULL DEFAULT 0.0")
        if "score_breakdown" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN score_breakdown TEXT")
        if "llm_summary" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN llm_summary TEXT")
        if "related_tickers" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN related_tickers TEXT")
        if "cross_references" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN cross_references TEXT")
        if "cross_ref_summary" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN cross_ref_summary TEXT")
        # Who wrote llm_summary: "ai:<model>" for a checked Gemini summary, "template" otherwise.
        if "summary_origin" not in columns:
            conn.execute("ALTER TABLE news_items ADD COLUMN summary_origin TEXT")

        # What each SEC filing says, read once from the SEC and kept so it is never fetched twice.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS filing_details (
                accession TEXT PRIMARY KEY,
                headline TEXT,
                detail TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Long monthly price history, one row per ticker, replaced whole on each good fetch
        # (see pipeline/prices.py).
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS price_history (
                symbol TEXT PRIMARY KEY,
                name TEXT,
                kind TEXT NOT NULL,
                months_json TEXT NOT NULL,
                price REAL NOT NULL,
                price_date TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                source TEXT NOT NULL DEFAULT 'yahoo'
            )
            """
        )
        # The close of the trading day before the price, and the past year's dividends per share.
        # Both are optional: NULL means not known, never zero.
        price_columns = [row[1] for row in conn.execute("PRAGMA table_info(price_history)").fetchall()]
        if "previous_close" not in price_columns:
            conn.execute("ALTER TABLE price_history ADD COLUMN previous_close REAL")
        if "previous_date" not in price_columns:
            conn.execute("ALTER TABLE price_history ADD COLUMN previous_date TEXT")
        if "dividends_json" not in price_columns:
            conn.execute("ALTER TABLE price_history ADD COLUMN dividends_json TEXT")

        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_published_date ON news_items(published_date DESC);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_ticker ON news_items(ticker);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_source ON news_items(source);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_score ON news_items(score DESC);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_news_category ON news_items(category);"
        )
    conn.close()
