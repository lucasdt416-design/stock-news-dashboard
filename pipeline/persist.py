"""Persistence layer for saving and querying scored news items and filings in SQLite."""

from typing import Any, Dict, List, Optional, Tuple
from pipeline.db import get_db_connection, init_db


def save_news_items(
    items: List[Dict[str, Any]], db_path: Optional[str] = None
) -> Tuple[int, int]:
    """Save a list of scored and deduplicated news items into SQLite database.

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
                INSERT INTO news_items (
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
                    raw_id,
                    category,
                    score,
                    score_breakdown,
                    llm_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_uid) DO UPDATE SET
                    category = excluded.category,
                    score = excluded.score,
                    score_breakdown = excluded.score_breakdown,
                    llm_summary = excluded.llm_summary,
                    headline = excluded.headline,
                    summary = excluded.summary
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
                    it.get("category"),
                    float(it.get("score", 0.0)),
                    it.get("score_breakdown"),
                    it.get("llm_summary"),
                ),
            )
            if cursor.rowcount > 0:
                new_count += 1

    conn.close()
    return (new_count, len(items))


def get_all_news_items(
    ticker: Optional[str] = None,
    source: Optional[str] = None,
    category: Optional[str] = None,
    order_by: str = "score",
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve news items sorted by score or publication date."""
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

    if category:
        conditions.append("category = ?")
        params.append(category)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    if order_by == "date":
        query += " ORDER BY published_date DESC, score DESC, id DESC"
    else:
        # Default order by score (highest impact first) then recency
        query += " ORDER BY score DESC, published_date DESC, id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_top_priority_items(
    limit: int = 8, min_score: Optional[float] = None, db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve top highest-impact priority items (5-10 items)."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    query = "SELECT * FROM news_items"
    params: List[Any] = []

    if min_score is not None:
        query += " WHERE score >= ?"
        params.append(min_score)

    query += " ORDER BY score DESC, published_date DESC, id DESC LIMIT ?"
    params.append(limit)

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_news_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve summary counts for tickers, sources, categories, and priority metrics."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    total_cursor = conn.execute("SELECT COUNT(*) AS total FROM news_items")
    total = total_cursor.fetchone()["total"]

    high_priority_cursor = conn.execute(
        "SELECT COUNT(*) AS count FROM news_items WHERE score >= 7.0"
    )
    high_priority_count = high_priority_cursor.fetchone()["count"]

    avg_score_cursor = conn.execute("SELECT AVG(score) AS avg_score FROM news_items")
    avg_score_raw = avg_score_cursor.fetchone()["avg_score"]
    avg_score = round(avg_score_raw, 1) if avg_score_raw is not None else 0.0

    ticker_cursor = conn.execute(
        "SELECT ticker, COUNT(*) AS count FROM news_items GROUP BY ticker ORDER BY count DESC"
    )
    by_ticker = {row["ticker"]: row["count"] for row in ticker_cursor.fetchall()}

    source_cursor = conn.execute(
        "SELECT source_label, COUNT(*) AS count FROM news_items GROUP BY source_label ORDER BY count DESC"
    )
    by_source = {row["source_label"]: row["count"] for row in source_cursor.fetchall()}

    category_cursor = conn.execute(
        "SELECT category, COUNT(*) AS count FROM news_items GROUP BY category ORDER BY count DESC"
    )
    by_category = {row["category"]: row["count"] for row in category_cursor.fetchall() if row["category"]}

    latest_cursor = conn.execute(
        "SELECT MAX(published_date) AS latest_date FROM news_items"
    )
    latest_date = latest_cursor.fetchone()["latest_date"]

    conn.close()
    return {
        "total": total,
        "high_priority_count": high_priority_count,
        "avg_score": avg_score,
        "by_ticker": by_ticker,
        "by_source": by_source,
        "by_category": by_category,
        "latest_date": latest_date,
    }
