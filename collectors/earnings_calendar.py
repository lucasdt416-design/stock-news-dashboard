"""Finnhub Structured Corporate Earnings Calendar Collector.

Fetches confirmed upcoming quarterly earnings release dates, reporting times
(Before Open / After Close), fiscal periods, and consensus EPS/revenue estimates
directly from Finnhub's /calendar/earnings endpoint.
"""

import datetime
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

FINNHUB_EARNINGS_URL = "https://finnhub.io/api/v1/calendar/earnings"
DEFAULT_USER_AGENT = "StockNewsDashboard/1.0"


def format_revenue(val: Optional[float]) -> str:
    """Format large numeric revenue values into readable strings (e.g. $108.1B, $950M)."""
    if val is None or val == 0:
        return "N/A"
    try:
        val = float(val)
        if abs(val) >= 1e12:
            return f"${val / 1e12:.2f}T"
        elif abs(val) >= 1e9:
            return f"${val / 1e9:.2f}B"
        elif abs(val) >= 1e6:
            return f"${val / 1e6:.1f}M"
        return f"${val:,.0f}"
    except Exception:
        return "N/A"


def format_hour_timing(hour: Optional[str]) -> str:
    """Map Finnhub hour codes to human-readable market sessions."""
    if not hour:
        return "Scheduled"
    h = hour.lower().strip()
    if h == "bmo":
        return "Before Market Open"
    elif h == "amc":
        return "After Market Close"
    elif h == "dmh":
        return "During Market Hours"
    return "Scheduled"


def fetch_ticker_earnings_calendar(
    symbol: str,
    api_key: str,
    from_date: str,
    to_date: str,
    timeout: int = 10,
) -> List[Dict[str, Any]]:
    """Query Finnhub /calendar/earnings endpoint for a specific symbol."""
    if not api_key:
        return []

    url = f"{FINNHUB_EARNINGS_URL}?symbol={symbol}&from={from_date}&to={to_date}&token={api_key}"
    req = urllib.request.Request(url, headers={"User-Agent": DEFAULT_USER_AGENT})

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
            return data.get("earningsCalendar", []) or []
    except urllib.error.HTTPError as e:
        if e.code == 401:
            logger.error("Finnhub 401 Unauthorized: Invalid FINNHUB_API_KEY")
        elif e.code == 429:
            logger.warning("Finnhub 429 Rate Limit reached for earnings calendar %s", symbol)
        else:
            logger.error("HTTP error fetching Finnhub earnings for %s: %s", symbol, e)
        return []
    except Exception as e:
        logger.error("Error fetching Finnhub earnings calendar for %s: %s", symbol, e)
        return []


def collect_finnhub_earnings_calendar(
    watchlist: List[Dict[str, Any]],
    api_key: Optional[str] = None,
    days_forward: int = 120,
    delay_seconds: float = 0.08,
    today: Optional[datetime.date] = None,
) -> List[Dict[str, Any]]:
    """Collect structured upcoming earnings events for all watchlist tickers.

    Returns normalized calendar event dictionaries ready for persistence and display.
    """
    token = api_key or os.environ.get("FINNHUB_API_KEY", "").strip()
    if not token:
        logger.warning(
            "FINNHUB_API_KEY not configured. Skipping Finnhub structured earnings calendar."
        )
        return []

    if today is None:
        today = datetime.date.today()

    from_date_str = today.strftime("%Y-%m-%d")
    to_date_str = (today + datetime.timedelta(days=days_forward)).strftime("%Y-%m-%d")

    events: List[Dict[str, Any]] = []

    # Map symbols to company names
    company_name_map = {}
    for entry in watchlist:
        sym = entry.get("symbol", "").upper()
        if sym:
            company_name_map[sym] = entry.get("name", sym)

    for entry in watchlist:
        symbol = entry.get("symbol", "").upper()
        if not symbol:
            continue

        company_name = company_name_map.get(symbol, symbol)
        raw_events = fetch_ticker_earnings_calendar(
            symbol=symbol,
            api_key=token,
            from_date=from_date_str,
            to_date=to_date_str,
        )

        for ev in raw_events:
            ev_date_str = ev.get("date")
            if not ev_date_str:
                continue

            # Ensure event is today or future
            try:
                ev_dt = datetime.date.fromisoformat(ev_date_str)
                if ev_dt < today:
                    continue
            except Exception:
                continue

            quarter = ev.get("quarter")
            year = ev.get("year")
            hour = ev.get("hour", "")
            hour_label = format_hour_timing(hour)

            eps_est = ev.get("epsEstimate")
            rev_est = ev.get("revenueEstimate")

            period_label = ""
            if quarter and year:
                period_label = f"Q{quarter} {year} "
            elif year:
                period_label = f"FY{year} "

            headline = f"{company_name} {period_label}Earnings Release ({hour_label})"
            if len(headline) > 95:
                headline = headline[:92] + "..."

            detail_parts = []
            if eps_est is not None:
                detail_parts.append(f"Consensus EPS Est: ${eps_est:.2f}")
            if rev_est is not None and rev_est > 0:
                detail_parts.append(f"Consensus Rev Est: {format_revenue(rev_est)}")
            detail_parts.append(f"Reporting: {hour_label}")

            details = " | ".join(detail_parts)

            # Standard calendar item representation
            events.append({
                "ticker": symbol,
                "company_name": company_name,
                "event_type": "Earnings Call / Results",
                "source_type": "SOURCED",
                "event_date": ev_date_str,
                "display_date": ev_dt.strftime("%b %d, %Y"),
                "headline": headline,
                "details": details,
                "source_url": f"https://finnhub.io/quote/{symbol}",
                "quarter": quarter,
                "year": year,
                "eps_estimate": eps_est,
                "revenue_estimate": rev_est,
                "hour": hour,
            })

        if delay_seconds > 0:
            time.sleep(delay_seconds)

    logger.info(
        "Finnhub Earnings Calendar: retrieved %d structured upcoming earnings events across %d tickers",
        len(events),
        len(watchlist),
    )
    return events
