"""Persistence layer for saving and querying SEC filings in SQLite."""

from typing import Any, Dict, List, Optional, Tuple
from pipeline.db import get_db_connection, init_db


def save_filings(filings: List[Dict[str, Any]], db_path: Optional[str] = None) -> Tuple[int, int]:
    """Save a list of filing dicts into SQLite database.

    Returns:
        tuple (new_inserted_count, total_processed_count)
    """
    if not filings:
        return (0, 0)

    init_db(db_path)
    conn = get_db_connection(db_path)
    new_count = 0

    with conn:
        for f in filings:
            cursor = conn.execute(
                """
                INSERT OR IGNORE INTO filings (
                    ticker,
                    company_name,
                    cik,
                    form,
                    filing_date,
                    report_date,
                    acceptance_date_time,
                    accession_number,
                    primary_doc_name,
                    primary_doc_description,
                    url
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    f.get("ticker"),
                    f.get("company_name"),
                    f.get("cik"),
                    f.get("form"),
                    f.get("filing_date"),
                    f.get("report_date"),
                    f.get("acceptance_date_time"),
                    f.get("accession_number"),
                    f.get("primary_doc_name"),
                    f.get("primary_doc_description"),
                    f.get("url"),
                ),
            )
            if cursor.rowcount > 0:
                new_count += 1

    conn.close()
    return (new_count, len(filings))


def get_all_filings(
    ticker: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Retrieve filings sorted newest first."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    query = "SELECT * FROM filings"
    params: List[Any] = []

    if ticker:
        query += " WHERE ticker = ?"
        params.append(ticker.upper())

    query += " ORDER BY filing_date DESC, acceptance_date_time DESC, id DESC"

    if limit is not None:
        query += " LIMIT ?"
        params.append(limit)

    cursor = conn.execute(query, params)
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_filing_stats(db_path: Optional[str] = None) -> Dict[str, Any]:
    """Retrieve summary counts for tickers and forms."""
    init_db(db_path)
    conn = get_db_connection(db_path)

    total_cursor = conn.execute("SELECT COUNT(*) AS total FROM filings")
    total = total_cursor.fetchone()["total"]

    ticker_cursor = conn.execute(
        "SELECT ticker, COUNT(*) AS count FROM filings GROUP BY ticker ORDER BY count DESC"
    )
    by_ticker = {row["ticker"]: row["count"] for row in ticker_cursor.fetchall()}

    form_cursor = conn.execute(
        "SELECT form, COUNT(*) AS count FROM filings GROUP BY form ORDER BY count DESC"
    )
    by_form = {row["form"]: row["count"] for row in form_cursor.fetchall()}

    latest_cursor = conn.execute(
        "SELECT MAX(filing_date) AS latest_date FROM filings"
    )
    latest_date = latest_cursor.fetchone()["latest_date"]

    conn.close()
    return {
        "total": total,
        "by_ticker": by_ticker,
        "by_form": by_form,
        "latest_date": latest_date,
    }
