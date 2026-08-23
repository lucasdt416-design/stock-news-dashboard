"""Database connection and schema management for stock news dashboard."""

import os
import sqlite3
from typing import Optional

DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "dashboard.db")


def get_db_connection(db_path: Optional[str] = None) -> sqlite3.Connection:
    """Return a connection to the SQLite database with Row factory enabled."""
    target_path = db_path or DEFAULT_DB_PATH
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    conn = sqlite3.connect(target_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Optional[str] = None) -> None:
    """Initialize database schema if tables do not exist."""
    conn = get_db_connection(db_path)
    with conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS filings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker TEXT NOT NULL,
                company_name TEXT,
                cik TEXT NOT NULL,
                form TEXT NOT NULL,
                filing_date TEXT NOT NULL,
                report_date TEXT,
                acceptance_date_time TEXT,
                accession_number TEXT UNIQUE NOT NULL,
                primary_doc_name TEXT,
                primary_doc_description TEXT,
                url TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_filings_filing_date ON filings(filing_date DESC);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_filings_ticker ON filings(ticker);"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_filings_form ON filings(form);"
        )
    conn.close()
