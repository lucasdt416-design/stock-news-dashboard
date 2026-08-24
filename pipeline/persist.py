"""Persistence layer for saving and querying scored news items and filings in SQLite."""

import logging
from typing import Any, Dict, List, Optional, Tuple
from pipeline.db import get_db_connection, init_db

logger = logging.getLogger(__name__)


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


def get_chart_data(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve aggregated data series for Chart.js rendering."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    # 1. Category Breakdown
    cat_cursor = conn.execute(
        """
        SELECT category, COUNT(*) AS count
        FROM news_items
        WHERE category IS NOT NULL AND category != ''
        GROUP BY category
        ORDER BY count DESC
        """
    )
    cat_rows = cat_cursor.fetchall()
    categories = [r["category"] for r in cat_rows]
    category_counts = [r["count"] for r in cat_rows]

    # 2. Timeline Frequency per Ticker
    time_cursor = conn.execute(
        """
        SELECT published_date, ticker, COUNT(*) AS count
        FROM news_items
        WHERE published_date IS NOT NULL AND published_date != ''
        GROUP BY published_date, ticker
        ORDER BY published_date ASC
        """
    )
    time_rows = time_cursor.fetchall()

    # Collect unique sorted dates (take last 14 most recent active dates)
    all_dates_set = sorted(list({r["published_date"] for r in time_rows}))
    recent_dates = all_dates_set[-14:] if len(all_dates_set) > 14 else all_dates_set

    # Priority order for watchlist tickers
    preferred_order = [
        "NVDA", "AAPL", "MSFT", "GOOGL", "AMZN", "META", "TSLA",
        "JPM", "JNJ", "XOM", "WMT", "DIS", "KO", "PFE", "BA"
    ]
    ticker_cursor = conn.execute(
        "SELECT DISTINCT ticker FROM news_items"
    )
    found_tickers = {r["ticker"] for r in ticker_cursor.fetchall()}
    tickers_list = [t for t in preferred_order if t in found_tickers] + sorted(
        list(found_tickers - set(preferred_order))
    )

    ticker_date_map: Dict[str, Dict[str, int]] = {
        t: {d: 0 for d in recent_dates} for t in tickers_list
    }

    for r in time_rows:
        d = r["published_date"]
        t = r["ticker"]
        if d in recent_dates and t in ticker_date_map:
            ticker_date_map[t][d] = r["count"]

    timeline_series = {
        t: [ticker_date_map[t].get(d, 0) for d in recent_dates]
        for t in tickers_list
    }

    # Short date label (MM/DD)
    date_labels = [d[5:] if len(d) >= 10 else d for d in recent_dates]

    conn.close()
    return {
        "categories": categories,
        "category_counts": category_counts,
        "timeline_dates": date_labels,
        "timeline_series": timeline_series,
    }


def get_recent_pipeline_runs(limit: int = 5, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Retrieve recent pipeline run telemetry reports from SQLite."""
    conn = get_db_connection(db_path)
    try:
        # Check if table exists
        check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='pipeline_runs'"
        ).fetchone()
        if not check:
            conn.close()
            return []

        cursor = conn.execute(
            """
            SELECT id, run_timestamp, edgar_count, company_ir_count,
                   total_raw, total_unique, high_impact_count,
                   status, health_message, moving_avg_raw
            FROM pipeline_runs
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning("Could not fetch pipeline runs: %s", e)
        conn.close()
        return []


def get_latest_pipeline_run(db_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Retrieve the most recent pipeline run telemetry report."""
    runs = get_recent_pipeline_runs(limit=1, db_path=db_path)
    return runs[0] if runs else None


def get_forthcoming_calendar(
    limit: int = 24, db_path: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Retrieve forthcoming corporate calendar events sorted by soonest date first."""
    conn = get_db_connection(db_path)
    try:
        check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='calendar_events'"
        ).fetchone()
        if not check:
            conn.close()
            return []

        cursor = conn.execute(
            """
            SELECT id, ticker, company_name, event_type, source_type, event_date,
                   display_date, relative_badge, headline, details, source_url
            FROM calendar_events
            ORDER BY event_date ASC, ticker ASC
            LIMIT ?
            """,
            (limit,),
        )
        rows = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return rows
    except Exception as e:
        logger.warning("Could not fetch calendar events: %s", e)
        conn.close()
        return []


def get_economic_indicators(
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve macroeconomic indicators with relevant watchlist ticker mappings from SQLite."""
    conn = get_db_connection(db_path)
    try:
        check = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='economic_indicators'"
        ).fetchone()
        if not check:
            conn.close()
            return []

        cursor = conn.execute(
            """
            SELECT indicator_id, name, series_id, category, current_value,
                   formatted_value, unit, previous_value, change_value,
                   change_direction, observation_date, updated_at,
                   context_note, relevant_tickers
            FROM economic_indicators
            ORDER BY 
                CASE indicator_id
                    WHEN 'interest_rates' THEN 1
                    WHEN 'inflation' THEN 2
                    WHEN 'unemployment' THEN 3
                    ELSE 4
                END
            """
        )
        rows = []
        for r in cursor.fetchall():
            d = dict(r)
            raw_tickers = d.get("relevant_tickers") or ""
            d["tickers_list"] = [t.strip() for t in raw_tickers.split(",") if t.strip()]
            rows.append(d)
        conn.close()
        return rows
    except Exception as e:
        logger.warning("Could not fetch economic indicators: %s", e)
        conn.close()
        return []
