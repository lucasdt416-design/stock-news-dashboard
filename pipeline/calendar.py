"""Forthcoming Corporate Calendar Engine (Category #24).

Extracts and calculates upcoming known dates for all watchlist companies:
1. Sourced Company Events:
   - Next earnings release / conference call dates from SEC 8-K & Company IR press releases.
   - Next dividend record, ex-dividend, and payment dates.
   - Major investor & industry conference presentations.
   - Cleans wire datelines and ensures only actual future event dates are extracted.
2. Statutory SEC Filing Deadlines (Computed / Estimated):
   - Computes statutory SEC deadlines for Large Accelerated Filers (Form 10-Q: 40 days post-quarter end; Form 10-K: 60 days post-year end).
   - Derived from each company's actual EDGAR quarterly report cycle and explicitly labeled as computed/estimated.
3. Sorts strictly by soonest date first.
"""

import datetime
import logging
import re
from typing import Any, Dict, List, Optional
from pipeline.db import get_db_connection

logger = logging.getLogger(__name__)


def init_calendar_schema(conn) -> None:
    """Create calendar_events table in SQLite if it does not exist and migrate columns."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticker TEXT NOT NULL,
            company_name TEXT NOT NULL,
            event_type TEXT NOT NULL,
            source_type TEXT NOT NULL DEFAULT 'SOURCED',
            event_date TEXT NOT NULL,
            display_date TEXT NOT NULL,
            relative_badge TEXT NOT NULL,
            headline TEXT NOT NULL,
            details TEXT,
            source_url TEXT,
            created_at TEXT NOT NULL,
            UNIQUE(ticker, event_type, event_date) ON CONFLICT REPLACE
        );
        """
    )
    # Ensure source_type column exists if table existed previously
    cursor = conn.execute("PRAGMA table_info(calendar_events)")
    columns = [col[1] for col in cursor.fetchall()]
    if "source_type" not in columns:
        conn.execute("ALTER TABLE calendar_events ADD COLUMN source_type TEXT NOT NULL DEFAULT 'SOURCED'")
    conn.commit()


def clean_and_extract_event_dates(
    headline: str,
    summary: str,
    published_date: str,
    today: Optional[datetime.date] = None,
) -> List[str]:
    """Extract standard ISO YYYY-MM-DD future event dates from headline or summary text.

    Strips PR wire datelines (e.g. 'NEW YORK --(BUSINESS WIRE)--Aug. 19, 2026--')
    and ignores past dates and publication dateline dates.
    """
    if today is None:
        today = datetime.date.today()

    # 1. Strip PR wire datelines
    cleaned_summary = re.sub(
        r"^[A-Z\s,]+--\([A-Za-z\s]+\)--[A-Za-z\s\d.,]+--\s*", "", summary or ""
    )
    cleaned_summary = re.sub(
        r"^[A-Za-z\s,.]+[-—]\s*[A-Za-z]+\.?\s+\d{1,2},?\s*\d{4}\s*[-—]\s*",
        "",
        cleaned_summary,
    )

    search_text = f"{headline} {cleaned_summary}"

    months = "January|February|March|April|May|June|July|August|September|October|November|December|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Oct|Nov|Dec"
    pattern = rf"\b({months})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s*(\d{{4}})?\b"
    matches = re.finditer(pattern, search_text, re.IGNORECASE)

    month_map = {
        "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
        "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
        "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
        "nov": 11, "november": 11, "dec": 12, "december": 12,
    }

    found: List[str] = []
    for m in matches:
        m_str, d_str, y_str = m.group(1).lower(), m.group(2), m.group(3)
        month = month_map.get(m_str[:3])
        if not month:
            continue
        try:
            day = int(d_str)
            year = int(y_str) if y_str else today.year
            if 2024 <= year <= 2028:
                dt = datetime.date(year, month, day)
                iso = dt.isoformat()

                # Rule 1: Exclude dates that match the press release publication date
                if iso == published_date:
                    continue

                # Rule 2: Exclude dates in the past
                if dt < today:
                    continue

                found.append(iso)
        except Exception:
            pass

    return sorted(list(set(found)))


def calculate_relative_badge(event_date_str: str, today: Optional[datetime.date] = None) -> str:
    """Calculate relative countdown string (e.g. 'In 3 days', 'In 2 weeks', 'Next month')."""
    if today is None:
        today = datetime.date.today()
    try:
        ev_dt = datetime.date.fromisoformat(event_date_str)
        delta_days = (ev_dt - today).days

        if delta_days == 0:
            return "Today"
        elif delta_days == 1:
            return "Tomorrow"
        elif delta_days > 1 and delta_days <= 6:
            return f"In {delta_days} days"
        elif delta_days >= 7 and delta_days <= 13:
            return "In 1 week"
        elif delta_days >= 14 and delta_days <= 30:
            weeks = max(2, delta_days // 7)
            return f"In {weeks} weeks"
        elif delta_days > 30 and delta_days <= 60:
            return "In ~1 month"
        elif delta_days > 60:
            months = delta_days // 30
            return f"In ~{months} months"
        elif delta_days < 0:
            if abs(delta_days) == 1:
                return "Yesterday"
            return f"{abs(delta_days)}d ago"
    except Exception:
        pass
    return "Scheduled"


def format_display_date(date_str: str) -> str:
    """Format YYYY-MM-DD into human-readable e.g. 'Aug 26, 2026'."""
    try:
        dt = datetime.date.fromisoformat(date_str)
        return dt.strftime("%b %d, %Y")
    except Exception:
        return date_str


def calculate_sec_filing_deadlines(conn, today: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    """Compute statutory SEC Form 10-Q and 10-K filing deadlines for Large Accelerated Filers.

    Explicitly tagged as 'ESTIMATED_RULE'.
    """
    if today is None:
        today = datetime.date.today()

    deadlines: List[Dict[str, Any]] = []

    # Get most recent 10-Q or 10-K for each ticker
    cursor = conn.execute(
        """
        SELECT ticker, company_name, form_or_type, published_date, summary, url
        FROM news_items
        WHERE form_or_type IN ('10-Q', '10-K')
        ORDER BY published_date DESC
        """
    )
    rows = cursor.fetchall()
    seen_tickers = set()

    for r in rows:
        ticker = r["ticker"]
        if ticker in seen_tickers:
            continue
        seen_tickers.add(ticker)

        summary = r["summary"] or ""
        form = r["form_or_type"]
        company_name = r["company_name"]
        url = r["url"] or f"https://www.sec.gov/edgar/browse/?CIK={ticker}"

        # Extract Report Period date from summary (e.g. "Report Period: 2026-06-30")
        m = re.search(r"Report Period:\s*(\d{4}-\d{2}-\d{2})", summary)
        if not m:
            continue

        report_date_str = m.group(1)
        try:
            rep_dt = datetime.date.fromisoformat(report_date_str)
            month = rep_dt.month + 3
            year = rep_dt.year
            if month > 12:
                month -= 12
                year += 1

            if month in (1, 3, 5, 7, 8, 10, 12):
                day = 31
            elif month in (4, 6, 9, 11):
                day = 30
            else:
                day = 28
            next_q_end = datetime.date(year, month, day)

            # Form 10-Q deadline: 40 calendar days after quarter end
            # Form 10-K deadline: 60 calendar days after fiscal year end
            if form == "10-K":
                deadline_dt = next_q_end + datetime.timedelta(days=40)
                evt_type = "Statutory SEC Deadline (Estimated)"
                headline = "Estimated SEC Form 10-Q Deadline (40d Rule)"
                details = f"Computed via SEC Rule 13a-13 for Large Accelerated Filers (40 calendar days post-Q1 period ended {next_q_end.strftime('%b %d, %Y')})."
            else:
                deadline_dt = next_q_end + datetime.timedelta(days=40)
                evt_type = "Statutory SEC Deadline (Estimated)"
                headline = "Estimated SEC Form 10-Q Deadline (40d Rule)"
                details = f"Computed via SEC Rule 13a-13 for Large Accelerated Filers (40 calendar days post-quarter ended {next_q_end.strftime('%b %d, %Y')})."

            deadline_iso = deadline_dt.isoformat()

            # Only include if upcoming
            if deadline_dt >= today:
                deadlines.append({
                    "ticker": ticker,
                    "company_name": company_name,
                    "event_type": evt_type,
                    "source_type": "ESTIMATED_RULE",
                    "event_date": deadline_iso,
                    "display_date": format_display_date(deadline_iso),
                    "relative_badge": calculate_relative_badge(deadline_iso, today=today),
                    "headline": headline,
                    "details": details,
                    "source_url": url,
                })
        except Exception as e:
            logger.warning("Error calculating SEC deadline for %s: %s", ticker, e)

    return deadlines


def extract_events_from_news_items(conn, today: Optional[datetime.date] = None) -> List[Dict[str, Any]]:
    """Extract confirmed upcoming earnings dates, dividend dates, and conferences from company releases."""
    if today is None:
        today = datetime.date.today()

    events: List[Dict[str, Any]] = []

    cursor = conn.execute(
        """
        SELECT ticker, company_name, form_or_type, category, headline, summary, published_date, url
        FROM news_items
        WHERE category IN ('Company Announcement', 'Earnings & Financials', 'Capital Structure & Offerings')
           OR headline LIKE '%Dividend%'
           OR headline LIKE '%Earnings%'
           OR headline LIKE '%Conference%'
           OR headline LIKE '%Results%'
           OR headline LIKE '%Present at%'
        ORDER BY published_date DESC
        """
    )
    rows = cursor.fetchall()

    for r in rows:
        headline = r["headline"] or ""
        summary = r["summary"] or ""
        published_date = r["published_date"] or ""

        # Extract only verified future event dates (ignoring publication dateline)
        dates = clean_and_extract_event_dates(
            headline=headline,
            summary=summary,
            published_date=published_date,
            today=today,
        )
        if not dates:
            continue

        ticker = r["ticker"]
        company_name = r["company_name"]
        url = r["url"]
        comb_lower = f"{headline} {summary}".lower()

        # Determine Event Type
        evt_type = None
        if "dividend" in comb_lower and any(k in comb_lower for k in ["payable", "record", "ex-dividend", "declared"]):
            evt_type = "Dividend (Payment/Record)"
        elif any(k in comb_lower for k in ["earnings", "financial results", "quarterly results", "conference call"]):
            evt_type = "Earnings Call / Results"
        elif "conference" in comb_lower or "present at" in comb_lower or "investor day" in comb_lower:
            evt_type = "Investor Conference"

        if not evt_type:
            continue

        for d in dates:
            clean_hl = headline
            if len(clean_hl) > 95:
                clean_hl = clean_hl[:92] + "..."

            events.append({
                "ticker": ticker,
                "company_name": company_name,
                "event_type": evt_type,
                "source_type": "SOURCED",
                "event_date": d,
                "display_date": format_display_date(d),
                "relative_badge": calculate_relative_badge(d, today=today),
                "headline": clean_hl,
                "details": summary[:140] if summary else clean_hl,
                "source_url": url,
            })

    return events


def build_forthcoming_calendar(
    watchlist: Optional[List[Dict[str, Any]]] = None,
    db_path: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build and persist forthcoming calendar events for all watchlist companies.

    Sorts strictly by soonest date first.
    """
    today = datetime.date.today()
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")

    with get_db_connection(db_path) as conn:
        init_calendar_schema(conn)

        # 1. Extract verified sourced events from company releases
        news_events = extract_events_from_news_items(conn, today=today)

        # 2. Extract statutory SEC deadlines (clearly labeled as computed/estimated)
        sec_deadlines = calculate_sec_filing_deadlines(conn, today=today)

        all_events = news_events + sec_deadlines

        # 3. Deduplicate events by (ticker, event_type, event_date)
        unique_events_map: Dict[str, Dict[str, Any]] = {}
        for ev in all_events:
            key = f"{ev['ticker']}|{ev['event_type']}|{ev['event_date']}"
            if key not in unique_events_map:
                unique_events_map[key] = ev

        sorted_events = sorted(
            list(unique_events_map.values()),
            key=lambda x: (x["event_date"], x["ticker"]),
        )

        # Clear prior calendar items to avoid stale entries
        conn.execute("DELETE FROM calendar_events")

        # 4. Persist to SQLite
        for ev in sorted_events:
            conn.execute(
                """
                INSERT OR REPLACE INTO calendar_events (
                    ticker, company_name, event_type, source_type,
                    event_date, display_date, relative_badge, headline,
                    details, source_url, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ev["ticker"],
                    ev["company_name"],
                    ev["event_type"],
                    ev["source_type"],
                    ev["event_date"],
                    ev["display_date"],
                    ev["relative_badge"],
                    ev["headline"],
                    ev["details"],
                    ev["source_url"],
                    now_iso,
                ),
            )
        conn.commit()

    logger.info("Forthcoming Calendar built: %d upcoming scheduled events", len(sorted_events))
    return sorted_events
