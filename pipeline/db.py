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
