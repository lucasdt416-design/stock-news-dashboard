"""Persistence layer for saving and querying news items and filings in SQLite."""

from typing import Any, Dict, List, Optional, Tuple
from pipeline.db import get_db_connection, init_db


def save_news_items(
    items: List[Dict[str, Any]], db_path: Optional[str] = None
) -> Tuple[int, int]:
    """Save a list of normalized and deduplicated news items into SQLite database.

    Returns:
        tuple (new_inserted_count, total_processed_count)
    """
    if not items:
        return (0, 0)

    init_db(db_path)
    conn = get_db_connection(db_path)
    new_count = 0

    with conn:
        for it in items:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO news_items (
                    item_uid,
                    ticker,
                    company_name,
                    source,
                    source_label,
                    source_type,
                    headline,
                    summary,
                    url,
                    published_date,
                    published_time,
                    form_or_type,
                    raw_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    it.get("item_uid"),
                    it.get("ticker"),
                    it.get("company_name"),
                    it.get("source"),
                    it.get("source_label", it.get("source")),
                    it.get("source_type", "news"),
                    it.get("headline"),
                    it.get("summary"),
                    it.get("url"),
                    it.get("published_date"),
                    it.get("published_time"),
                    it.get("form_or_type"),
                    it.get("raw_id"),
                ),
            )
            if cursor.rowcount > 0:
                new_count += 1

    conn.close()
    return (new_count, len(items))


def get_all_news_items(
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve news items sorted newest first."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    query = "SELECT * FROM news_items"
    conditions = []
    params: List[Any] = []

    if ticker:
        conditions.append("ticker = ?")
        params.append(ticker.upper())

    if source:
        conditions.append("source = ?")
        params.append(source.lower())

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY published_date DESC, published_time DESC, id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_news_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve summary counts for tickers, sources, and latest dates."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    total_cursor = conn.execute("SELECT COUNT(*) AS total FROM news_items")
    total = total_cursor.fetchone()["total"]

    ticker_cursor = conn.execute(
        "SELECT ticker, COUNT(*) AS count FROM news_items GROUP BY ticker ORDER BY count DESC"
    )
    by_ticker = {row["ticker"]: row["count"] for row in ticker_cursor.fetchall()}

    source_cursor = conn.execute(
        "SELECT source_label, COUNT(*) AS count FROM news_items GROUP BY source_label ORDER BY count DESC"
    )
    by_source = {row["source_label"]: row["count"] for row in source_cursor.fetchall()}

    latest_cursor = conn.execute(
        "SELECT MAX(published_date) AS latest_date FROM news_items"
    )
    latest_date = latest_cursor.fetchone()["latest_date"]

    conn.close()
    return {
        "total": total,
        "by_ticker": by_ticker,
        "by_source": by_source,
        "latest_date": latest_date,
    }
